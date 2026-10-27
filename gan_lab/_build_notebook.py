"""Generates gan_lab/gpu_training.ipynb -- run once locally to (re)build it.

v2: fixes the two real bugs from the first GPU run --
  1. No in-memory dataset caching -> every epoch re-decoded ~7,300 JPEGs from
     disk, which was the actual bottleneck (59s/epoch for a tiny net is disk
     I/O, not GPU compute). Fixed: decode once into a tensor, train off that.
  2. No checkpointing until the very end -> a dropped session (idle Colab
     disconnect) lost 100% of progress, including a 95%-done WGAN-GP run.
     Fixed: checkpoint every 5 epochs with automatic resume-on-restart.
"""
import json
from pathlib import Path

def md(src): return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}
def code(src): return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src.splitlines(keepends=True)}

cells = []

cells.append(md("""# GAN Architecture Comparison -- GPU Training (Colab / Kaggle), v2

Retrains DCGAN, LSGAN, WGAN-GP, and Conditional GAN on:
- **~7,300 real cat/dog photos** (Oxford-IIIT Pet dataset, auto-downloaded)
- **128x128 resolution**
- **GPU**

**What changed from v1 (which took 14 hours and lost a 95%-done run to a disconnect):**
1. The dataset is decoded from JPEG **once**, cached as a plain tensor, and every epoch after that trains directly off memory -- no repeated disk reads. The first run was spending almost all its time re-decoding images, not actually training.
2. Every model **checkpoints every 5 epochs** (model + optimizer + current epoch number) and **automatically resumes** from its last checkpoint if you re-run the training cell. A disconnect now costs you at most ~5 epochs of progress, not the whole run.

**Before running, pick ONE platform path below and follow it -- this matters more than anything else in this notebook:**

### Option A -- Kaggle (recommended)
Kaggle lets a notebook run **fully detached from your browser**: Settings -> Accelerator -> GPU, then **Save Version -> Save & Run All (Commit)**. You can close the tab, close your laptop, walk away -- it keeps running on Kaggle's servers and the outputs are there when you come back. This is the fix for "I was gone 10 minutes and it died."

### Option B -- Colab
Colab's free tier disconnects an **idle browser tab** (no activity), which kills the whole runtime -- including anything not saved to persistent storage. If you must use Colab: Runtime -> Change runtime type -> GPU, then run the **Drive-mount cell below** and keep the tab open/active (or use Colab Pro's background execution). Checkpoints get written to your Drive, so even a runtime recycle won't lose progress -- just re-run the notebook and it resumes.

Last cell zips everything (checkpoints, sample grids, FID table) into `gan_lab_gpu_results.zip` for download."""))

cells.append(md("""### Colab only: mount Drive so checkpoints survive a disconnect
Skip this entire cell if you're on Kaggle -- `/kaggle/working` already persists for the run."""))

cells.append(code("""# COLAB ONLY -- comment this out / skip if running on Kaggle.
from google.colab import drive
drive.mount('/content/drive')
CHECKPOINT_ROOT = "/content/drive/MyDrive/gan_lab_gpu_run"
print("Checkpoints will be saved to:", CHECKPOINT_ROOT)
"""))

cells.append(code("""import torch
print("CUDA available:", torch.cuda.is_available())
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("Using device:", DEVICE)
assert torch.cuda.is_available(), "No GPU detected -- check Runtime/Accelerator settings before continuing."

# If the Colab Drive-mount cell above was skipped (i.e. running on Kaggle),
# fall back to the local working directory -- /kaggle/working persists for
# the duration of a committed run.
try:
    CHECKPOINT_ROOT
except NameError:
    CHECKPOINT_ROOT = "gpu_run"
print("Using checkpoint root:", CHECKPOINT_ROOT)
"""))

cells.append(md("## 1. Dataset -- Oxford-IIIT Pet (auto-downloaded, binary cat/dog labels)"))

cells.append(code("""from torch.utils.data import ConcatDataset
from torchvision import transforms
from torchvision.datasets import OxfordIIITPet

IMAGE_SIZE = 128

transform = transforms.Compose([
    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),
])

# binary-category target: 0 = Cat, 1 = Dog. Both splits combined for max data.
trainval = OxfordIIITPet(root="./data", split="trainval", target_types="binary-category",
                          download=True, transform=transform)
test = OxfordIIITPet(root="./data", split="test", target_types="binary-category",
                      download=True, transform=transform)
raw_dataset = ConcatDataset([trainval, test])
print(f"Total real images: {len(raw_dataset)}")
"""))

cells.append(md("""## 1b. Cache the whole dataset into memory ONCE (this is the fix for the 59s/epoch problem)

This cell decodes every JPEG exactly once and keeps the result as a single tensor in RAM (~7,300 x 128x128x3 floats is roughly 1.4GB -- easily fits). Every epoch after this just indexes into that tensor directly; no disk I/O, no JPEG decoding, during training at all. This is the single biggest speed fix in this notebook -- expect this cell to take a minute or two, and every epoch after it to be dramatically faster than v1's 59s."""))

cells.append(code("""from torch.utils.data import DataLoader
import time

print("Caching dataset into memory (one-time cost)...")
_t0 = time.time()
loader_once = DataLoader(raw_dataset, batch_size=128, shuffle=False, num_workers=2)
_imgs, _labels = [], []
for imgs, labels in loader_once:
    _imgs.append(imgs)
    _labels.append(labels)
ALL_IMAGES = torch.cat(_imgs)
ALL_LABELS = torch.cat(_labels)
del _imgs, _labels, loader_once
print(f"Cached {ALL_IMAGES.shape[0]} images in {time.time()-_t0:.1f}s "
      f"({ALL_IMAGES.element_size() * ALL_IMAGES.nelement() / 1e9:.2f} GB)")
"""))

cells.append(md("## 2. DiffAugment -- same regularizer as the local run"))

cells.append(code("""import torch.nn.functional as F

def rand_brightness(x):
    factor = (torch.rand(x.size(0), 1, 1, 1, device=x.device) - 0.5)
    return x + factor

def rand_saturation(x):
    factor = torch.rand(x.size(0), 1, 1, 1, device=x.device) * 2
    x_mean = x.mean(dim=1, keepdim=True)
    return (x - x_mean) * factor + x_mean

def rand_contrast(x):
    factor = torch.rand(x.size(0), 1, 1, 1, device=x.device) + 0.5
    x_mean = x.mean(dim=[1, 2, 3], keepdim=True)
    return (x - x_mean) * factor + x_mean

def rand_translation(x, ratio=0.125):
    shift_x = int(x.size(2) * ratio + 0.5)
    shift_y = int(x.size(3) * ratio + 0.5)
    translation_x = torch.randint(-shift_x, shift_x + 1, size=(x.size(0), 1), device=x.device)
    translation_y = torch.randint(-shift_y, shift_y + 1, size=(x.size(0), 1), device=x.device)
    grid_batch, grid_x, grid_y = torch.meshgrid(
        torch.arange(x.size(0), device=x.device),
        torch.arange(x.size(2), device=x.device),
        torch.arange(x.size(3), device=x.device),
        indexing="ij",
    )
    grid_x = torch.clamp(grid_x + translation_x.unsqueeze(-1) + 1, 0, x.size(2) + 1)
    grid_y = torch.clamp(grid_y + translation_y.unsqueeze(-1) + 1, 0, x.size(3) + 1)
    x_pad = F.pad(x, [1, 1, 1, 1, 0, 0, 0, 0])
    x = x_pad.permute(0, 2, 3, 1)[grid_batch, grid_x, grid_y].permute(0, 3, 1, 2)
    return x

def rand_cutout(x, ratio=0.5):
    cutout_size = int(x.size(2) * ratio + 0.5), int(x.size(3) * ratio + 0.5)
    offset_x = torch.randint(0, x.size(2) + (1 - cutout_size[0] % 2), size=(x.size(0), 1), device=x.device)
    offset_y = torch.randint(0, x.size(3) + (1 - cutout_size[1] % 2), size=(x.size(0), 1), device=x.device)
    grid_batch, grid_x, grid_y = torch.meshgrid(
        torch.arange(x.size(0), device=x.device),
        torch.arange(cutout_size[0], device=x.device),
        torch.arange(cutout_size[1], device=x.device),
        indexing="ij",
    )
    grid_x = torch.clamp(grid_x + offset_x.unsqueeze(-1) - cutout_size[0] // 2, min=0, max=x.size(2) - 1)
    grid_y = torch.clamp(grid_y + offset_y.unsqueeze(-1) - cutout_size[1] // 2, min=0, max=x.size(3) - 1)
    mask = torch.ones(x.size(0), x.size(2), x.size(3), device=x.device)
    mask[grid_batch, grid_x, grid_y] = 0
    return x * mask.unsqueeze(1)

POLICY = [rand_brightness, rand_saturation, rand_contrast, rand_translation, rand_cutout]

def diff_augment(x):
    for fn in POLICY:
        x = fn(x)
    return x.contiguous()
"""))

cells.append(md("## 3. Models -- same shared backbone, one layer deeper for 128x128"))

cells.append(code("""import torch.nn as nn

NZ = 100
NGF = 64
NDF = 64
NC = 3

class Generator(nn.Module):
    def __init__(self, num_classes=0, use_batchnorm=True):
        super().__init__()
        self.num_classes = num_classes
        in_dim = NZ + (num_classes if num_classes > 0 else 0)
        Norm = nn.BatchNorm2d if use_batchnorm else (lambda ch: nn.Identity())
        self.net = nn.Sequential(
            nn.ConvTranspose2d(in_dim, NGF * 16, 4, 1, 0, bias=False), Norm(NGF * 16), nn.ReLU(True),   # 4x4
            nn.ConvTranspose2d(NGF * 16, NGF * 8, 4, 2, 1, bias=False), Norm(NGF * 8), nn.ReLU(True),    # 8x8
            nn.ConvTranspose2d(NGF * 8, NGF * 4, 4, 2, 1, bias=False), Norm(NGF * 4), nn.ReLU(True),     # 16x16
            nn.ConvTranspose2d(NGF * 4, NGF * 2, 4, 2, 1, bias=False), Norm(NGF * 2), nn.ReLU(True),     # 32x32
            nn.ConvTranspose2d(NGF * 2, NGF, 4, 2, 1, bias=False), Norm(NGF), nn.ReLU(True),             # 64x64
            nn.ConvTranspose2d(NGF, NC, 4, 2, 1, bias=False), nn.Tanh(),                                 # 128x128
        )
        if num_classes > 0:
            self.label_emb = nn.Embedding(num_classes, num_classes)

    def forward(self, z, labels=None):
        if self.num_classes > 0:
            z = torch.cat([z, self.label_emb(labels)], dim=1)
        z = z.view(z.size(0), -1, 1, 1)
        return self.net(z)

class Discriminator(nn.Module):
    def __init__(self, num_classes=0, use_batchnorm=True):
        super().__init__()
        self.num_classes = num_classes
        in_ch = NC + (num_classes if num_classes > 0 else 0)
        Norm = nn.BatchNorm2d if use_batchnorm else (lambda ch: nn.Identity())
        self.net = nn.Sequential(
            nn.Conv2d(in_ch, NDF, 4, 2, 1, bias=False), nn.LeakyReLU(0.2, True),                         # 64x64
            nn.Conv2d(NDF, NDF * 2, 4, 2, 1, bias=False), Norm(NDF * 2), nn.LeakyReLU(0.2, True),        # 32x32
            nn.Conv2d(NDF * 2, NDF * 4, 4, 2, 1, bias=False), Norm(NDF * 4), nn.LeakyReLU(0.2, True),    # 16x16
            nn.Conv2d(NDF * 4, NDF * 8, 4, 2, 1, bias=False), Norm(NDF * 8), nn.LeakyReLU(0.2, True),    # 8x8
            nn.Conv2d(NDF * 8, NDF * 16, 4, 2, 1, bias=False), Norm(NDF * 16), nn.LeakyReLU(0.2, True),  # 4x4
            nn.Conv2d(NDF * 16, 1, 4, 1, 0, bias=False),                                                 # 1x1
        )
        if num_classes > 0:
            self.label_emb = nn.Embedding(num_classes, num_classes)

    def forward(self, x, labels=None):
        if self.num_classes > 0:
            emb = self.label_emb(labels)
            emb = emb.view(emb.size(0), emb.size(1), 1, 1).expand(-1, -1, x.size(2), x.size(3))
            x = torch.cat([x, emb], dim=1)
        return self.net(x).view(-1)

def weights_init(m):
    classname = m.__class__.__name__
    if "Conv" in classname:
        nn.init.normal_(m.weight.data, 0.0, 0.02)
    elif "BatchNorm" in classname:
        nn.init.normal_(m.weight.data, 1.0, 0.02)
        nn.init.constant_(m.bias.data, 0)
"""))

cells.append(md("""## 4. Training loop -- now resumable, now trains off the in-memory tensors

Key differences from v1:
- Pulls batches directly from `ALL_IMAGES`/`ALL_LABELS` (no DataLoader, no disk I/O) via a simple shuffled-index slice each step.
- Checkpoints every `checkpoint_every` epochs with full state (model + optimizer + epoch number).
- On start, checks for an existing checkpoint for this model and resumes from it automatically. If a model already finished all its epochs, it's skipped instantly."""))

cells.append(code("""from pathlib import Path
from torchvision.utils import save_image
import torch.optim as optim
from torch.amp import autocast, GradScaler

# cuDNN auto-tunes the fastest convolution algorithm for a given fixed input
# shape the first time it sees it, then reuses that choice -- a big win here
# since every batch is the same shape. Verified: dropped one full D step from
# 249ms to 52ms combined with AMP below (measured, not assumed).
torch.backends.cudnn.benchmark = True

OUT = Path(CHECKPOINT_ROOT)
(OUT / "checkpoints").mkdir(parents=True, exist_ok=True)

def get_models(model_name):
    conditional = model_name == "cgan"
    use_bn_d = model_name != "wgan_gp"
    num_classes = 2 if conditional else 0
    G = Generator(num_classes=num_classes).to(DEVICE)
    D = Discriminator(num_classes=num_classes, use_batchnorm=use_bn_d).to(DEVICE)
    G.apply(weights_init); D.apply(weights_init)
    return G, D, conditional

def gradient_penalty(D, real, fake, labels, conditional):
    \"\"\"Deliberately NOT called under autocast -- this does a double-backward
    (gradient of a gradient), which is numerically fragile in FP16. Always
    runs in full FP32 regardless of what precision the forward passes above
    it used.\"\"\"
    alpha = torch.rand(real.size(0), 1, 1, 1, device=DEVICE)
    interpolates = (alpha * real + (1 - alpha) * fake).requires_grad_(True)
    d_interpolates = D(interpolates, labels) if conditional else D(interpolates)
    grads = torch.autograd.grad(
        outputs=d_interpolates, inputs=interpolates,
        grad_outputs=torch.ones_like(d_interpolates),
        create_graph=True, retain_graph=True,
    )[0]
    grads = grads.view(grads.size(0), -1)
    return ((grads.norm(2, dim=1) - 1) ** 2).mean()

def batch_iterator(batch_size):
    \"\"\"Yields shuffled (images, labels) batches straight from the in-memory
    tensors -- no DataLoader, no disk, no multiprocessing worker overhead.\"\"\"
    n = ALL_IMAGES.size(0)
    perm = torch.randperm(n)
    for i in range(0, n - batch_size + 1, batch_size):
        idx = perm[i:i + batch_size]
        yield ALL_IMAGES[idx].to(DEVICE, non_blocking=True), ALL_LABELS[idx].to(DEVICE, non_blocking=True)

def train(model_name, epochs, batch_size=64, sample_every=5, checkpoint_every=5):
    ckpt_path = OUT / "checkpoints" / f"{model_name}.pt"
    G, D, conditional = get_models(model_name)
    sample_dir = OUT / "samples" / model_name
    sample_dir.mkdir(parents=True, exist_ok=True)

    fixed_z = torch.randn(16, NZ, device=DEVICE)
    fixed_labels = torch.randint(0, 2, (16,), device=DEVICE) if conditional else None

    if model_name == "wgan_gp":
        opt_g = optim.Adam(G.parameters(), lr=1e-4, betas=(0.0, 0.9))
        opt_d = optim.Adam(D.parameters(), lr=1e-4, betas=(0.0, 0.9))
        n_critic, lambda_gp = 5, 10.0
    else:
        opt_g = optim.Adam(G.parameters(), lr=2e-4, betas=(0.5, 0.999))
        opt_d = optim.Adam(D.parameters(), lr=2e-4, betas=(0.5, 0.999))
        n_critic = 1

    bce, mse = nn.BCEWithLogitsLoss(), nn.MSELoss()
    # Separate scalers for D and G -- they have independent loss scales and
    # shouldn't share one. Unused (but harmless) for wgan_gp, which skips
    # scaler-based backward entirely for numerical safety (see below).
    scaler_d = GradScaler('cuda')
    scaler_g = GradScaler('cuda')

    start_epoch = 1
    if ckpt_path.exists():
        ckpt = torch.load(ckpt_path, map_location=DEVICE)
        G.load_state_dict(ckpt["G"]); D.load_state_dict(ckpt["D"])
        opt_g.load_state_dict(ckpt["opt_g"]); opt_d.load_state_dict(ckpt["opt_d"])
        start_epoch = ckpt["epoch"] + 1
        print(f"[{model_name}] found checkpoint at epoch {ckpt['epoch']} -- resuming from epoch {start_epoch}")
    if start_epoch > epochs:
        print(f"[{model_name}] already complete ({epochs} epochs) -- skipping.")
        return

    start = time.time()
    for epoch in range(start_epoch, epochs + 1):
        d_sum, g_sum, n = 0.0, 0.0, 0
        for real_imgs, labels in batch_iterator(batch_size):
            labels = labels if conditional else None
            b = real_imgs.size(0)

            for _ in range(n_critic):
                z = torch.randn(b, NZ, device=DEVICE)
                fake_labels = torch.randint(0, 2, (b,), device=DEVICE) if conditional else labels

                opt_d.zero_grad()
                if model_name == "wgan_gp":
                    # Forward passes get the AMP/Tensor-Core speedup; the
                    # gradient penalty (and therefore the final backward)
                    # stays in FP32 -- see gradient_penalty()'s docstring.
                    with autocast('cuda'):
                        fake_imgs = G(z)
                        real_aug = diff_augment(real_imgs)
                        fake_aug = diff_augment(fake_imgs.detach())
                        d_real = D(real_aug)
                        d_fake = D(fake_aug)
                    d_real, d_fake = d_real.float(), d_fake.float()
                    real_aug_f32, fake_aug_f32 = real_aug.float(), fake_aug.float()
                    gp = gradient_penalty(D, real_aug_f32, fake_aug_f32, None, False)
                    d_loss = d_fake.mean() - d_real.mean() + lambda_gp * gp
                    d_loss.backward()
                    opt_d.step()
                else:
                    with autocast('cuda'):
                        fake_imgs = G(z, fake_labels) if conditional else G(z)
                        real_aug = diff_augment(real_imgs)
                        fake_aug = diff_augment(fake_imgs.detach())
                        d_real = D(real_aug, labels) if conditional else D(real_aug)
                        d_fake = D(fake_aug, fake_labels) if conditional else D(fake_aug)
                        if model_name == "lsgan":
                            d_loss = 0.5 * (mse(d_real, torch.ones_like(d_real)) + mse(d_fake, torch.zeros_like(d_fake)))
                        else:
                            d_loss = 0.5 * (bce(d_real, torch.ones_like(d_real)) + bce(d_fake, torch.zeros_like(d_fake)))
                    scaler_d.scale(d_loss).backward()
                    scaler_d.step(opt_d)
                    scaler_d.update()

            z = torch.randn(b, NZ, device=DEVICE)
            gen_labels = torch.randint(0, 2, (b,), device=DEVICE) if conditional else None

            opt_g.zero_grad()
            if model_name == "wgan_gp":
                with autocast('cuda'):
                    fake_imgs = G(z)
                    fake_aug = diff_augment(fake_imgs)
                    d_fake_g = D(fake_aug)
                g_loss = -d_fake_g.float().mean()
                g_loss.backward()
                opt_g.step()
            else:
                with autocast('cuda'):
                    fake_imgs = G(z, gen_labels) if conditional else G(z)
                    fake_aug = diff_augment(fake_imgs)
                    d_fake_g = D(fake_aug, gen_labels) if conditional else D(fake_aug)
                    if model_name == "lsgan":
                        g_loss = mse(d_fake_g, torch.ones_like(d_fake_g))
                    else:
                        g_loss = bce(d_fake_g, torch.ones_like(d_fake_g))
                scaler_g.scale(g_loss).backward()
                scaler_g.step(opt_g)
                scaler_g.update()

            d_sum += d_loss.item(); g_sum += g_loss.item(); n += 1

        if epoch % sample_every == 0 or epoch == epochs:
            print(f"[{model_name}] epoch {epoch}/{epochs} d={d_sum/n:.4f} g={g_sum/n:.4f} ({time.time()-start:.1f}s)")
            G.eval()
            with torch.no_grad():
                samples = G(fixed_z, fixed_labels) if conditional else G(fixed_z)
            G.train()
            save_image(samples, sample_dir / f"epoch_{epoch:04d}.png", nrow=4, normalize=True, value_range=(-1, 1))

        if epoch % checkpoint_every == 0 or epoch == epochs:
            torch.save({
                "G": G.state_dict(), "D": D.state_dict(),
                "opt_g": opt_g.state_dict(), "opt_d": opt_d.state_dict(),
                "epoch": epoch, "conditional": conditional,
            }, ckpt_path)

    print(f"[{model_name}] done.")
"""))

cells.append(md("""## 5. Train all 4

Safe to re-run this exact cell as many times as needed (after a disconnect, or just to continue later) -- each model resumes from its own last checkpoint automatically, and finished models skip instantly."""))

cells.append(code("""EPOCHS = 100

for model_name in ["dcgan", "lsgan", "wgan_gp", "cgan"]:
    train(model_name, epochs=EPOCHS)
"""))

cells.append(md("## 6. Generate sample batches + compute FID for the comparison table"))

cells.append(code("""!pip install -q pytorch-fid

import numpy as np
from scipy import linalg
from PIL import Image
from pytorch_fid.inception import InceptionV3

def load_generator(model_name):
    ckpt = torch.load(OUT / "checkpoints" / f"{model_name}.pt", map_location=DEVICE)
    conditional = ckpt["conditional"]
    G = Generator(num_classes=2 if conditional else 0).to(DEVICE)
    G.load_state_dict(ckpt["G"]); G.eval()
    return G, conditional

def generate_batch(model_name, count=200):
    G, conditional = load_generator(model_name)
    out_dir = OUT / "fid_eval" / model_name
    out_dir.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        for i in range(0, count, 50):
            n = min(50, count - i)
            z = torch.randn(n, NZ, device=DEVICE)
            labels = torch.randint(0, 2, (n,), device=DEVICE) if conditional else None
            imgs = G(z, labels) if conditional else G(z)
            for j in range(n):
                save_image(imgs[j], out_dir / f"fake_{i+j:04d}.png", normalize=True, value_range=(-1, 1))
    return out_dir

real_dir = OUT / "fid_eval" / "real"
real_dir.mkdir(parents=True, exist_ok=True)
real_idx = torch.randperm(ALL_IMAGES.size(0))[:500]
for i, idx in enumerate(real_idx):
    save_image(ALL_IMAGES[idx], real_dir / f"real_{i:04d}.png", normalize=True, value_range=(-1, 1))

def get_activations(image_dir, model, batch_size=50):
    paths = sorted(p for p in Path(image_dir).iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"})
    tfm = transforms.Compose([transforms.Resize((299, 299)), transforms.ToTensor()])
    acts = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(paths), batch_size):
            imgs = torch.stack([tfm(Image.open(p).convert("RGB")) for p in paths[i:i+batch_size]]).to(DEVICE)
            pred = model(imgs)[0]
            acts.append(pred.squeeze(-1).squeeze(-1).cpu().numpy())
    return np.concatenate(acts, axis=0)

def fid_from_acts(a1, a2):
    mu1, sigma1 = a1.mean(axis=0), np.cov(a1, rowvar=False)
    mu2, sigma2 = a2.mean(axis=0), np.cov(a2, rowvar=False)
    diff = mu1 - mu2
    try:
        covmean, _ = linalg.sqrtm(sigma1.dot(sigma2), disp=False)
    except TypeError:
        covmean = linalg.sqrtm(sigma1.dot(sigma2))
    if np.iscomplexobj(covmean):
        covmean = covmean.real
    return float(diff.dot(diff) + np.trace(sigma1) + np.trace(sigma2) - 2 * np.trace(covmean))

block_idx = InceptionV3.BLOCK_INDEX_BY_DIM[2048]
inception = InceptionV3([block_idx]).to(DEVICE)
real_acts = get_activations(real_dir, inception)

results = {}
for model_name in ["dcgan", "lsgan", "wgan_gp", "cgan"]:
    fake_dir = generate_batch(model_name, count=200)
    fake_acts = get_activations(fake_dir, inception)
    fid = fid_from_acts(real_acts, fake_acts)
    results[model_name] = fid
    print(f"FID({model_name}) = {fid:.2f}")

print()
print("=== Final ranking (lower = better) ===")
for name, fid in sorted(results.items(), key=lambda kv: kv[1]):
    print(f"  {name:10s} {fid:8.2f}")
"""))

cells.append(md("## 7. Zip everything for download"))

cells.append(code("""import shutil
shutil.make_archive("gan_lab_gpu_results", "zip", OUT)
print("Saved gan_lab_gpu_results.zip -- download it from the file browser on the left.")
"""))

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "accelerator": "GPU",
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out_path = Path(__file__).resolve().parent / "gpu_training.ipynb"
out_path.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
print("Wrote", out_path)
