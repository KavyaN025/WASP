"""
anti_gan_data.py

Dataset for the anti-GAN (content authenticity) detector: real = label 0,
GAN-fake = label 1. Deliberately pulls fakes from ALL 4 trained
architectures (not just WGAN-GP, the one actually deployed for poisoning)
so the detector doesn't just memorize one generator's specific artifacts --
the whole point of this detector is catching fakes from a generator it may
not have trained against, matching the CNNDetection design (Wang et al.,
CVPR 2020) discussed in the literature survey.

Augmentation: random JPEG re-compression + random blur, applied only to
the training split -- the same trick Wang et al. use to make the detector
robust to post-processing rather than overfitting to pristine-PNG
artifacts specific to how these particular fakes were saved.
"""

import io
import random
from pathlib import Path

from PIL import Image
import torch
from torch.utils.data import Dataset
from torchvision import transforms

GPU_RESULTS = Path(__file__).resolve().parent / "gpu_results"
REAL_DIR = GPU_RESULTS / "fid_eval" / "real"
FAKE_DIRS = {
    "dcgan": GPU_RESULTS / "fid_eval" / "dcgan",
    "lsgan": GPU_RESULTS / "fid_eval" / "lsgan",
    "wgan_gp": GPU_RESULTS / "fid_eval" / "wgan_gp",
    "cgan": GPU_RESULTS / "fid_eval" / "cgan",
}
IMAGE_SIZE = 128


def _random_jpeg_blur(img: Image.Image) -> Image.Image:
    """Randomly re-compresses through JPEG at a random quality and/or
    applies a slight blur -- forces the detector to key off real generative
    artifacts rather than "this file was never JPEG-compressed" shortcuts."""
    if random.random() < 0.5:
        quality = random.randint(30, 95)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        img = Image.open(buf).convert("RGB")
    if random.random() < 0.3:
        img = img.filter(_blur_filter(random.uniform(0.5, 2.0)))
    return img


def _blur_filter(radius):
    from PIL import ImageFilter
    return ImageFilter.GaussianBlur(radius)


class AuthenticityDataset(Dataset):
    def __init__(self, train: bool = True, val_fraction: float = 0.15, seed: int = 42):
        real_paths = sorted(REAL_DIR.glob("*.png")) + sorted(REAL_DIR.glob("*.jpg"))
        fake_paths = []
        for model_name, d in FAKE_DIRS.items():
            fake_paths.extend(sorted(d.glob("*.png")) + sorted(d.glob("*.jpg")))

        rng = random.Random(seed)
        rng.shuffle(real_paths)
        rng.shuffle(fake_paths)

        def split(paths):
            n_val = max(1, int(len(paths) * val_fraction))
            return paths[n_val:] if train else paths[:n_val]

        real_split = split(real_paths)
        fake_split = split(fake_paths)

        self.samples = [(p, 0) for p in real_split] + [(p, 1) for p in fake_split]
        rng.shuffle(self.samples)
        self.train = train

        base_tfms = [
            transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        ]
        if train:
            base_tfms.append(transforms.RandomHorizontalFlip())
        self.resize_flip = transforms.Compose(base_tfms)
        self.to_tensor_norm = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),  # ImageNet stats, matches pretrained backbone
        ])

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        img = Image.open(path).convert("RGB")
        img = self.resize_flip(img)
        if self.train:
            img = _random_jpeg_blur(img)
        return self.to_tensor_norm(img), label


if __name__ == "__main__":
    train_ds = AuthenticityDataset(train=True)
    val_ds = AuthenticityDataset(train=False)
    print(f"train: {len(train_ds)} samples, val: {len(val_ds)} samples")
    n_real = sum(1 for _, l in train_ds.samples if l == 0)
    n_fake = sum(1 for _, l in train_ds.samples if l == 1)
    print(f"train split -- real: {n_real}, fake: {n_fake}")
