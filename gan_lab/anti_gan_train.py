"""
anti_gan_train.py

Trains the content-authenticity detector: a pretrained ResNet-18 fine-tuned
as a binary real-vs-GAN-fake classifier. This IS the "anti-GAN" -- a
separately-trained forensic model, not the co-trained discriminator from
any of the 4 generators, so it isn't overfit to one generator's specific
quirks (see anti_gan_data.py for why fakes from all 4 architectures are
mixed into training).

Usage:
    python anti_gan_train.py --epochs 10
"""

import argparse
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import models

from anti_gan_data import AuthenticityDataset

HERE = Path(__file__).resolve().parent
DEVICE = torch.device("cpu")


def build_model():
    model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    model.fc = nn.Linear(model.fc.in_features, 2)  # real=0, fake=1
    return model.to(DEVICE)


def evaluate(model, loader):
    model.eval()
    correct, total, loss_sum = 0, 0, 0.0
    criterion = nn.CrossEntropyLoss()
    with torch.no_grad():
        for imgs, labels in loader:
            imgs, labels = imgs.to(DEVICE), labels.to(DEVICE)
            logits = model(imgs)
            loss = criterion(logits, labels)
            loss_sum += loss.item() * imgs.size(0)
            preds = logits.argmax(dim=1)
            correct += (preds == labels).sum().item()
            total += imgs.size(0)
    model.train()
    return loss_sum / total, correct / total


def train(epochs: int, batch_size: int = 32, lr: float = 1e-4):
    train_ds = AuthenticityDataset(train=True)
    val_ds = AuthenticityDataset(train=False)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    print(f"train={len(train_ds)} val={len(val_ds)}")

    model = build_model()
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    best_val_acc = 0.0
    ckpt_path = HERE / "anti_gan_checkpoint.pt"

    start = time.time()
    for epoch in range(1, epochs + 1):
        train_loss_sum, train_correct, train_total = 0.0, 0, 0
        for imgs, labels in train_loader:
            imgs, labels = imgs.to(DEVICE), labels.to(DEVICE)
            optimizer.zero_grad()
            logits = model(imgs)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

            train_loss_sum += loss.item() * imgs.size(0)
            train_correct += (logits.argmax(dim=1) == labels).sum().item()
            train_total += imgs.size(0)

        val_loss, val_acc = evaluate(model, val_loader)
        train_acc = train_correct / train_total
        print(f"epoch {epoch}/{epochs} train_loss={train_loss_sum/train_total:.4f} "
              f"train_acc={train_acc:.3f} val_loss={val_loss:.4f} val_acc={val_acc:.3f} "
              f"({time.time()-start:.1f}s)")

        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            torch.save({"model": model.state_dict(), "val_acc": val_acc, "epoch": epoch}, ckpt_path)

    print(f"best val_acc={best_val_acc:.3f} -- saved {ckpt_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()
    train(args.epochs, args.batch_size, args.lr)
