"""
train.py

Unified training loop for all 4 from-scratch candidates:
    python train.py --model dcgan
    python train.py --model lsgan
    python train.py --model wgan_gp
    python train.py --model cgan

Same data, same DiffAugment regularizer, same shared conv backbone
(models.py) for every one of them -- the only things that differ are the
loss function, whether the discriminator/critic uses batchnorm, and (for
cgan) whether class labels are threaded through. That keeps the survey's
4-way comparison fair: architecture-and-loss is the only variable.

Checkpoints -> gan_lab/checkpoints/<model>.pt
Sample grids (saved every few epochs, so training progress is visible)
    -> gan_lab/samples/<model>/epoch_NNN.png
"""

import argparse
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision.utils import save_image

from data import CatsDogsDataset
from diffaugment import diff_augment
from models import Generator, Discriminator, weights_init, NZ

HERE = Path(__file__).resolve().parent
DEVICE = torch.device("cpu")


def get_models(model_name: str):
    conditional = model_name == "cgan"
    use_bn_d = model_name != "wgan_gp"  # WGAN-GP's gradient penalty assumes per-sample
                                        # Lipschitz behavior; batchnorm mixes statistics
                                        # across the batch and breaks that assumption.
    num_classes = 2 if conditional else 0
    G = Generator(num_classes=num_classes).to(DEVICE)
    D = Discriminator(num_classes=num_classes, use_batchnorm=use_bn_d).to(DEVICE)
    G.apply(weights_init)
    D.apply(weights_init)
    return G, D, conditional


def gradient_penalty(D, real, fake, labels, conditional):
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


def train(model_name: str, epochs: int, batch_size: int, sample_every: int):
    dataset = CatsDogsDataset()
    print(f"[{model_name}] dataset size: {len(dataset)} images")
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=True)

    G, D, conditional = get_models(model_name)

    sample_dir = HERE / "samples" / model_name
    sample_dir.mkdir(parents=True, exist_ok=True)

    fixed_z = torch.randn(16, NZ, device=DEVICE)
    fixed_labels = torch.randint(0, 2, (16,), device=DEVICE) if conditional else None

    if model_name == "wgan_gp":
        opt_g = optim.Adam(G.parameters(), lr=1e-4, betas=(0.0, 0.9))
        opt_d = optim.Adam(D.parameters(), lr=1e-4, betas=(0.0, 0.9))
        n_critic = 5
        lambda_gp = 10.0
    else:
        opt_g = optim.Adam(G.parameters(), lr=2e-4, betas=(0.5, 0.999))
        opt_d = optim.Adam(D.parameters(), lr=2e-4, betas=(0.5, 0.999))
        n_critic = 1

    bce = nn.BCEWithLogitsLoss()
    mse = nn.MSELoss()

    start = time.time()
    for epoch in range(1, epochs + 1):
        d_loss_sum, g_loss_sum, n_batches = 0.0, 0.0, 0

        for real_imgs, labels in loader:
            real_imgs = real_imgs.to(DEVICE)
            labels = labels.to(DEVICE) if conditional else None
            b = real_imgs.size(0)

            # ---- Discriminator / Critic step(s) ----
            for _ in range(n_critic):
                z = torch.randn(b, NZ, device=DEVICE)
                fake_labels = torch.randint(0, 2, (b,), device=DEVICE) if conditional else labels
                fake_imgs = G(z, fake_labels) if conditional else G(z)

                real_aug = diff_augment(real_imgs)
                fake_aug = diff_augment(fake_imgs.detach())

                opt_d.zero_grad()
                if model_name == "wgan_gp":
                    d_real = D(real_aug, labels) if conditional else D(real_aug)
                    d_fake = D(fake_aug, fake_labels) if conditional else D(fake_aug)
                    gp = gradient_penalty(D, real_aug, fake_aug, labels if conditional else None, conditional)
                    d_loss = d_fake.mean() - d_real.mean() + lambda_gp * gp
                elif model_name == "lsgan":
                    d_real = D(real_aug, labels) if conditional else D(real_aug)
                    d_fake = D(fake_aug, fake_labels) if conditional else D(fake_aug)
                    d_loss = 0.5 * (mse(d_real, torch.ones_like(d_real)) +
                                     mse(d_fake, torch.zeros_like(d_fake)))
                else:  # dcgan, cgan
                    d_real = D(real_aug, labels) if conditional else D(real_aug)
                    d_fake = D(fake_aug, fake_labels) if conditional else D(fake_aug)
                    d_loss = 0.5 * (bce(d_real, torch.ones_like(d_real)) +
                                     bce(d_fake, torch.zeros_like(d_fake)))
                d_loss.backward()
                opt_d.step()

            # ---- Generator step ----
            z = torch.randn(b, NZ, device=DEVICE)
            gen_labels = torch.randint(0, 2, (b,), device=DEVICE) if conditional else None
            fake_imgs = G(z, gen_labels) if conditional else G(z)
            fake_aug = diff_augment(fake_imgs)

            opt_g.zero_grad()
            if model_name == "wgan_gp":
                g_loss = -D(fake_aug, gen_labels).mean() if conditional else -D(fake_aug).mean()
            elif model_name == "lsgan":
                d_fake = D(fake_aug, gen_labels) if conditional else D(fake_aug)
                g_loss = mse(d_fake, torch.ones_like(d_fake))
            else:
                d_fake = D(fake_aug, gen_labels) if conditional else D(fake_aug)
                g_loss = bce(d_fake, torch.ones_like(d_fake))
            g_loss.backward()
            opt_g.step()

            d_loss_sum += d_loss.item()
            g_loss_sum += g_loss.item()
            n_batches += 1

        if epoch % max(1, sample_every) == 0 or epoch == epochs:
            elapsed = time.time() - start
            print(f"[{model_name}] epoch {epoch}/{epochs} "
                  f"d_loss={d_loss_sum/n_batches:.4f} g_loss={g_loss_sum/n_batches:.4f} "
                  f"({elapsed:.1f}s elapsed)")
            G.eval()
            with torch.no_grad():
                samples = G(fixed_z, fixed_labels) if conditional else G(fixed_z)
            G.train()
            save_image(samples, sample_dir / f"epoch_{epoch:04d}.png", nrow=4, normalize=True, value_range=(-1, 1))

    ckpt_path = HERE / "checkpoints" / f"{model_name}.pt"
    torch.save({"G": G.state_dict(), "D": D.state_dict(), "conditional": conditional}, ckpt_path)
    print(f"[{model_name}] saved checkpoint -> {ckpt_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["dcgan", "lsgan", "wgan_gp", "cgan"], required=True)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--sample-every", type=int, default=20)
    args = parser.parse_args()
    train(args.model, args.epochs, args.batch_size, args.sample_every)
