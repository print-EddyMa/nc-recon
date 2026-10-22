"""Siamese change classifier: one ResNet-18 encoder sees the pre and the post
chip; the head reads the post features and their difference from the pre
features, and outputs the five FEMA levels.

`pretrained=True` starts from torchvision's ImageNet weights (BSD-3-Clause
code; the ImageNet images carry their own research terms), `False` trains
from scratch for a strictly public-domain lineage. The model card records
which was used.
"""
from __future__ import annotations

import torch
from torch import nn

MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


class Siamese(nn.Module):
    def __init__(self, n_classes: int = 5, pretrained: bool = True, encoder_path: str | None = None):
        """`encoder_path`: load the ImageNet weights from this local file
        (no network). `pretrained=True` without a path lets torchvision fetch
        them, for training on a networked machine only."""
        super().__init__()
        from torchvision.models import ResNet18_Weights, resnet18

        enc = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1 if pretrained and not encoder_path else None)
        if encoder_path:
            sd = torch.load(encoder_path, map_location="cpu", weights_only=True)
            enc.load_state_dict(sd)
        enc.fc = nn.Identity()
        self.enc = enc
        self.head = nn.Sequential(nn.Linear(1024, 256), nn.ReLU(), nn.Dropout(0.3), nn.Linear(256, n_classes))
        self.min_px = 128
        self.register_buffer("mean", MEAN.clone())
        self.register_buffer("std", STD.clone())

    def forward(self, pre: torch.Tensor, post: torch.Tensor) -> torch.Tensor:
        """pre, post: float tensors in [0, 1], (N, 3, H, W)."""
        if pre.shape[-1] < self.min_px:
            # ResNet-18 downsamples 32x: a 64 px chip would end as 2x2 features
            pre = nn.functional.interpolate(pre, size=self.min_px, mode="bilinear", align_corners=False)
            post = nn.functional.interpolate(post, size=self.min_px, mode="bilinear", align_corners=False)
        a = self.enc((pre - self.mean) / self.std)
        b = self.enc((post - self.mean) / self.std)
        return self.head(torch.cat([b, b - a], dim=1))
