"""
models.py

Shared DCGAN-style conv backbone -- matches the architecture actually used
for the GPU training run (gpu_training.ipynb), one layer deeper than the
original 64x64 CPU run to support 128x128 output. Checkpoints from
gan_lab/gpu_results/checkpoints/*.pt (the deployed candidates) are only
loadable against THIS architecture, not the old 64x64 one.

- Generator: latent vector (+ optional class embedding) -> 128x128x3 image.
- Discriminator: 128x128x3 image (+ optional class embedding, injected as
  broadcast channels) -> one raw scalar (no sigmoid).
"""

import torch
import torch.nn as nn

NZ = 100       # latent vector size
NGF = 64       # generator feature map base width
NDF = 64       # discriminator feature map base width
NC = 3         # image channels
IMAGE_SIZE = 128


class Generator(nn.Module):
    def __init__(self, num_classes: int = 0, use_batchnorm: bool = True):
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
            if labels is None:
                raise ValueError("Conditional generator requires labels")
            z = torch.cat([z, self.label_emb(labels)], dim=1)
        z = z.view(z.size(0), -1, 1, 1)
        return self.net(z)


class Discriminator(nn.Module):
    def __init__(self, num_classes: int = 0, use_batchnorm: bool = True):
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
            if labels is None:
                raise ValueError("Conditional discriminator requires labels")
            emb = self.label_emb(labels)  # (B, num_classes)
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
