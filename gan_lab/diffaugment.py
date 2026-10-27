"""
diffaugment.py

Differentiable Augmentation for small-dataset GAN training (Zhao et al.,
"Differentiable Augmentation for Data-Efficient GAN Training", NeurIPS 2020).

Applied to BOTH real and fake batches, every training step, so gradients
flow through the augmentation back into the generator. This is the one
thing standing between "the discriminator memorizes our 100 photos in a
few hundred steps and the generator stops learning" and an actually
usable training run on a dataset this small.

Policy here = color + translation + cutout, the same default combination
used in the paper's own small-dataset experiments. Pure-tensor
implementation, no extra dependency beyond torch.
"""

import torch
import torch.nn.functional as F


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


def diff_augment(x: torch.Tensor) -> torch.Tensor:
    """Applies the full color+translation+cutout policy to a batch."""
    for fn in POLICY:
        x = fn(x)
    return x.contiguous()
