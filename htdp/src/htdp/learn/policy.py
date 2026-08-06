from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import torch
from torch import Tensor, nn

from htdp.learn.obs import ACTION_DIM, OBS_DIM, PROPRIO_DIM


@dataclass
class ACTConfig:
    obs_dim: int = OBS_DIM
    action_dim: int = ACTION_DIM
    chunk: int = 20
    hidden: int = 256
    heads: int = 4
    layers: int = 2


class ACTPolicy(nn.Module):
    """Compact action-chunking transformer: obs -> chunk of actions (deterministic)."""

    def __init__(self, cfg: ACTConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.obs_embed = nn.Linear(cfg.obs_dim, cfg.hidden)
        self.queries = nn.Parameter(torch.randn(cfg.chunk, cfg.hidden))
        layer = nn.TransformerDecoderLayer(
            d_model=cfg.hidden, nhead=cfg.heads, dim_feedforward=cfg.hidden * 4,
            batch_first=True,
        )
        self.decoder = nn.TransformerDecoder(layer, num_layers=cfg.layers)
        self.head = nn.Linear(cfg.hidden, cfg.action_dim)

    def forward(self, obs: Tensor) -> Tensor:
        b = obs.shape[0]
        memory = self.obs_embed(obs).unsqueeze(1)  # (B, 1, H)
        tgt = self.queries.unsqueeze(0).expand(b, -1, -1)  # (B, chunk, H)
        dec = self.decoder(tgt, memory)  # (B, chunk, H)
        return cast(Tensor, self.head(dec))  # (B, chunk, action_dim)

    @torch.no_grad()
    def act(self, obs: Tensor) -> Tensor:
        self.eval()
        return self.forward(obs.unsqueeze(0)).squeeze(0)


@dataclass
class VisuomotorACTConfig:
    proprio_dim: int = PROPRIO_DIM
    action_dim: int = ACTION_DIM
    chunk: int = 20
    hidden: int = 256
    heads: int = 4
    layers: int = 2
    image_size: int = 96
    img_feat: int = 128


class _ImageEncoder(nn.Module):
    """Small 3-stride CNN: (B,3,96,96) -> (B, img_feat). Localises the cube/target from pixels."""

    def __init__(self, img_feat: int) -> None:
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(3, 32, 5, stride=2, padding=2), nn.ReLU(),   # 96 -> 48
            nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.ReLU(),  # 48 -> 24
            nn.Conv2d(64, 128, 3, stride=2, padding=1), nn.ReLU(), # 24 -> 12
            nn.AdaptiveAvgPool2d(1),                               # -> (B,128,1,1)
        )
        self.proj = nn.Linear(128, img_feat)

    def forward(self, image: Tensor) -> Tensor:
        feat = self.conv(image).flatten(1)  # (B, 128)
        return cast(Tensor, self.proj(feat))  # (B, img_feat)


class VisuomotorACTPolicy(nn.Module):
    """Visuomotor action-chunking transformer: (image, proprio) -> chunk of actions.

    The privileged cube/target xyz are NOT inputs; the CNN must read them from the front-camera
    image. Image features are fused with proprioception into a single memory token, then the same
    decoder-with-learned-queries head as the state-based ACTPolicy produces the action chunk.
    """

    def __init__(self, cfg: VisuomotorACTConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.encoder = _ImageEncoder(cfg.img_feat)
        self.fuse = nn.Linear(cfg.img_feat + cfg.proprio_dim, cfg.hidden)
        self.queries = nn.Parameter(torch.randn(cfg.chunk, cfg.hidden))
        layer = nn.TransformerDecoderLayer(
            d_model=cfg.hidden, nhead=cfg.heads, dim_feedforward=cfg.hidden * 4,
            batch_first=True,
        )
        self.decoder = nn.TransformerDecoder(layer, num_layers=cfg.layers)
        self.head = nn.Linear(cfg.hidden, cfg.action_dim)

    def forward(self, image: Tensor, proprio: Tensor) -> Tensor:
        b = image.shape[0]
        img_feat = self.encoder(image)  # (B, img_feat)
        fused = self.fuse(torch.cat([img_feat, proprio], dim=1))  # (B, H)
        memory = fused.unsqueeze(1)  # (B, 1, H)
        tgt = self.queries.unsqueeze(0).expand(b, -1, -1)  # (B, chunk, H)
        dec = self.decoder(tgt, memory)  # (B, chunk, H)
        return cast(Tensor, self.head(dec))  # (B, chunk, action_dim)

    @torch.no_grad()
    def act(self, image: Tensor, proprio: Tensor) -> Tensor:
        self.eval()
        return self.forward(image.unsqueeze(0), proprio.unsqueeze(0)).squeeze(0)
