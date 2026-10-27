"""
anti_gan_infer.py

Inference-only helper around the trained anti-GAN checkpoint
(anti_gan_checkpoint.pt). Loaded once by wasp_lab/server/app.py and reused
for every Authenticity Score computation -- model stays in memory, no
reloading per request.

score_image(path) -> float in [0, 1]: probability the image is REAL.
Higher = more authentic. Below ~0.5 means the detector thinks it's a
GAN-generated fake.
"""

from pathlib import Path
from functools import lru_cache

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import models, transforms

HERE = Path(__file__).resolve().parent
CKPT_PATH = HERE / "anti_gan_checkpoint.pt"
DEVICE = torch.device("cpu")
IMAGE_SIZE = 128

_transform = transforms.Compose([
    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

_model = None


def _load_model():
    global _model
    if _model is not None:
        return _model
    if not CKPT_PATH.exists():
        raise FileNotFoundError(f"No anti-GAN checkpoint at {CKPT_PATH} -- run anti_gan_train.py first.")
    model = models.resnet18(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, 2)
    ckpt = torch.load(CKPT_PATH, map_location=DEVICE)
    model.load_state_dict(ckpt["model"])
    model.eval()
    _model = model
    return model


def is_available() -> bool:
    return CKPT_PATH.exists()


@lru_cache(maxsize=512)
def score_image_cached(path_str: str) -> float:
    """Cached by file path -- a given content file's authenticity score
    never changes, so this avoids re-running inference on the same
    filesystem object across repeated cache hits."""
    return score_image(Path(path_str))


def score_image(path: Path) -> float:
    model = _load_model()
    img = Image.open(path).convert("RGB")
    x = _transform(img).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        logits = model(x)
        probs = F.softmax(logits, dim=1)
    return float(probs[0, 0].item())  # P(real)


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(p, "->", round(score_image(Path(p)), 4))
