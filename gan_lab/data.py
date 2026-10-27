"""
data.py

Loads the real content catalog (wasp_lab/server/content/cats,
wasp_lab/server/content/dogs -- the same 50+50 images WASP's dashboard
serves as genuine ICN content) as a labeled image dataset for GAN
training: label 0 = cat, label 1 = dog.

Images are resized to a small, CPU-friendly resolution (64x64) and
normalized to [-1, 1] to match a tanh generator output.
"""

import os
from pathlib import Path

from PIL import Image
import torch
from torch.utils.data import Dataset
from torchvision import transforms

CONTENT_ROOT = Path(__file__).resolve().parent.parent / "wasp_lab" / "server" / "content"
CLASSES = ["cats", "dogs"]  # index = label
IMAGE_SIZE = 64

transform = transforms.Compose([
    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),  # -> [-1, 1]
])


class CatsDogsDataset(Dataset):
    """Every real image under content/cats and content/dogs, with its
    class label. Used as the "real" distribution for all 4 from-scratch
    GAN candidates (DCGAN/LSGAN/WGAN-GP/cGAN)."""

    def __init__(self, root: Path = CONTENT_ROOT, classes=CLASSES):
        self.samples = []
        for label, cls in enumerate(classes):
            folder = root / cls
            if not folder.is_dir():
                continue
            for fname in sorted(os.listdir(folder)):
                if os.path.splitext(fname)[1].lower() in {".jpg", ".jpeg", ".png"}:
                    self.samples.append((folder / fname, label))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        img = Image.open(path).convert("RGB")
        return transform(img), label


if __name__ == "__main__":
    ds = CatsDogsDataset()
    print(f"Loaded {len(ds)} images from {CONTENT_ROOT}")
    img, label = ds[0]
    print("sample tensor shape:", img.shape, "label:", label, CLASSES[label])
