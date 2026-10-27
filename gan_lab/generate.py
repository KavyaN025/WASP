"""
generate.py

Loads a trained checkpoint (gan_lab/checkpoints/<model>.pt) and samples N
fake images from it, saved as individual PNG files -- ready either for
visual inspection/FID scoring, or for deployment into WASP's mesh
topology as poisoned content (see wasp_lab/server/app.py's
"synthetic_content" loader, which picks these up).

Usage:
    python generate.py --model dcgan --count 20 --out samples_out/dcgan
    python generate.py --model cgan --count 20 --label 0 --out samples_out/cgan_cats
"""

import argparse
from pathlib import Path

import torch
from torchvision.utils import save_image

from models import Generator, NZ

HERE = Path(__file__).resolve().parent
DEVICE = torch.device("cpu")


def load_generator(model_name: str) -> Generator:
    ckpt_path = HERE / "gpu_results" / "checkpoints" / f"{model_name}.pt"
    if not ckpt_path.exists():
        raise FileNotFoundError(f"No checkpoint at {ckpt_path} -- train this model first.")
    ckpt = torch.load(ckpt_path, map_location=DEVICE)
    conditional = ckpt.get("conditional", False)
    G = Generator(num_classes=2 if conditional else 0).to(DEVICE)
    G.load_state_dict(ckpt["G"])
    G.eval()
    return G, conditional


def generate(model_name: str, count: int, out_dir: Path, label: int | None = None):
    G, conditional = load_generator(model_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    with torch.no_grad():
        z = torch.randn(count, NZ, device=DEVICE)
        if conditional:
            labels = torch.full((count,), label if label is not None else 0, device=DEVICE)
            imgs = G(z, labels)
        else:
            imgs = G(z)

    for i in range(count):
        save_image(imgs[i], out_dir / f"fake_{model_name}_{i:03d}.png", normalize=True, value_range=(-1, 1))

    print(f"[{model_name}] saved {count} fake images -> {out_dir}")
    return out_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["dcgan", "lsgan", "wgan_gp", "cgan"], required=True)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--label", type=int, choices=[0, 1], default=None, help="0=cat, 1=dog (cgan only)")
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()
    out_dir = Path(args.out) if args.out else HERE / "output" / args.model
    generate(args.model, args.count, out_dir, args.label)
