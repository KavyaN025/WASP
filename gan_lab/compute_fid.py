"""
compute_fid.py

pytorch-fid's own CLI breaks against the newer scipy in this venv
(scipy.linalg.sqrtm dropped the `disp` kwarg pytorch-fid still passes).
Reuses pytorch-fid's InceptionV3 feature extractor directly and does the
Frechet-distance math here instead, without that kwarg.
"""

import sys
from pathlib import Path

import numpy as np
import torch
from scipy import linalg
from PIL import Image
from torchvision import transforms
from pytorch_fid.inception import InceptionV3

DEVICE = torch.device("cpu")


def get_activations(image_dir: Path, model, batch_size=50):
    paths = sorted(
        p for p in image_dir.iterdir()
        if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
    tfm = transforms.Compose([
        transforms.Resize((299, 299)),
        transforms.ToTensor(),
    ])
    acts = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(paths), batch_size):
            batch_paths = paths[i:i + batch_size]
            imgs = torch.stack([tfm(Image.open(p).convert("RGB")) for p in batch_paths]).to(DEVICE)
            pred = model(imgs)[0]
            acts.append(pred.squeeze(-1).squeeze(-1).cpu().numpy())
    return np.concatenate(acts, axis=0)


def fid_from_acts(acts1, acts2):
    mu1, sigma1 = acts1.mean(axis=0), np.cov(acts1, rowvar=False)
    mu2, sigma2 = acts2.mean(axis=0), np.cov(acts2, rowvar=False)

    diff = mu1 - mu2
    try:
        covmean, _ = linalg.sqrtm(sigma1.dot(sigma2), disp=False)
    except TypeError:
        covmean = linalg.sqrtm(sigma1.dot(sigma2))
    if np.iscomplexobj(covmean):
        covmean = covmean.real
    return float(diff.dot(diff) + np.trace(sigma1) + np.trace(sigma2) - 2 * np.trace(covmean))


if __name__ == "__main__":
    real_dir = Path(sys.argv[1])
    fake_dir = Path(sys.argv[2])

    block_idx = InceptionV3.BLOCK_INDEX_BY_DIM[2048]
    model = InceptionV3([block_idx]).to(DEVICE)

    real_acts = get_activations(real_dir, model)
    fake_acts = get_activations(fake_dir, model)
    fid = fid_from_acts(real_acts, fake_acts)
    print(f"FID({real_dir.name} vs {fake_dir.name}) = {fid:.2f}")
