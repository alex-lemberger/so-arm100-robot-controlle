# src/htdp/learn/train.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import torch
from torch import Tensor

from htdp.learn.obs import PROPRIO_INDICES, proprio_from_state
from htdp.learn.policy import ACTConfig, ACTPolicy, VisuomotorACTConfig, VisuomotorACTPolicy


def pick_device() -> str:
    return "mps" if torch.backends.mps.is_available() else "cpu"


class Normalizer:
    def __init__(self, stats: dict[str, Any]) -> None:
        self.obs_mean = np.array(stats["observation.state"]["mean"], dtype=np.float32)
        self.obs_std = np.array(stats["observation.state"]["std"], dtype=np.float32)
        self.act_mean = np.array(stats["action"]["mean"], dtype=np.float32)
        self.act_std = np.array(stats["action"]["std"], dtype=np.float32)

    def normalize_obs(self, x: Tensor) -> Tensor:
        m = torch.as_tensor(self.obs_mean, device=x.device)
        s = torch.as_tensor(self.obs_std, device=x.device)
        return (x - m) / s

    def normalize_action(self, x: Tensor) -> Tensor:
        m = torch.as_tensor(self.act_mean, device=x.device)
        s = torch.as_tensor(self.act_std, device=x.device)
        return (x - m) / s

    def denormalize_action(self, x: Tensor) -> Tensor:
        m = torch.as_tensor(self.act_mean, device=x.device)
        s = torch.as_tensor(self.act_std, device=x.device)
        return x * s + m


def _build_samples(dataset_dir: Path, chunk: int):  # type: ignore[no-untyped-def]
    obs_list, tgt_list = [], []
    for ep in sorted((dataset_dir / "data" / "chunk-000").glob("episode_*.parquet")):
        df = pl.read_parquet(ep)
        obs = np.array(df["observation.state"].to_list(), dtype=np.float32)
        act = np.array(df["action"].to_list(), dtype=np.float32)
        n = len(obs)
        for t in range(n):
            chunk_act = act[t : t + chunk]
            if len(chunk_act) < chunk:  # pad by repeating the last action
                pad = np.repeat(act[-1:], chunk - len(chunk_act), axis=0)
                chunk_act = np.concatenate([chunk_act, pad], axis=0)
            obs_list.append(obs[t])
            tgt_list.append(chunk_act)
    return np.array(obs_list), np.array(tgt_list)


class VisuomotorNormalizer:
    """Proprio z-score + action z-score; images are normalized to [0,1] (uint8/255) at use."""

    def __init__(self, proprio_stats: dict[str, Any], action_stats: dict[str, Any]) -> None:
        self.prop_mean = np.array(proprio_stats["mean"], dtype=np.float32)
        self.prop_std = np.array(proprio_stats["std"], dtype=np.float32)
        self.act_mean = np.array(action_stats["mean"], dtype=np.float32)
        self.act_std = np.array(action_stats["std"], dtype=np.float32)

    def normalize_proprio(self, x: Tensor) -> Tensor:
        m = torch.as_tensor(self.prop_mean, device=x.device)
        s = torch.as_tensor(self.prop_std, device=x.device)
        return (x - m) / s

    def normalize_action(self, x: Tensor) -> Tensor:
        m = torch.as_tensor(self.act_mean, device=x.device)
        s = torch.as_tensor(self.act_std, device=x.device)
        return (x - m) / s

    def denormalize_action(self, x: Tensor) -> Tensor:
        m = torch.as_tensor(self.act_mean, device=x.device)
        s = torch.as_tensor(self.act_std, device=x.device)
        return x * s + m


def proprio_stats_from(full_obs_stats: dict[str, Any]) -> dict[str, list[float]]:
    """Slice the proprio subset out of the 17-dim observation.state stats (one source of truth)."""
    idx = np.array(PROPRIO_INDICES)
    return {k: np.array(full_obs_stats[k], dtype=np.float32)[idx].tolist() for k in full_obs_stats}


def _build_visuomotor_samples(dataset_dir: Path, chunk: int):  # type: ignore[no-untyped-def]
    """Returns (proprio (N,11) f32, images (N,96,96,3) u8, action_chunks (N,chunk,8) f32)."""
    prop_list, img_list, tgt_list = [], [], []
    for ep in sorted((dataset_dir / "data" / "chunk-000").glob("episode_*.parquet")):
        df = pl.read_parquet(ep)
        state = np.array(df["observation.state"].to_list(), dtype=np.float32)
        act = np.array(df["action"].to_list(), dtype=np.float32)
        imgs = np.load(ep.with_name(ep.stem + "_image.npy"))  # (T,96,96,3) uint8
        prop = proprio_from_state(state)  # (T, 11)
        n = len(state)
        for t in range(n):
            chunk_act = act[t : t + chunk]
            if len(chunk_act) < chunk:  # pad by repeating the last action
                pad = np.repeat(act[-1:], chunk - len(chunk_act), axis=0)
                chunk_act = np.concatenate([chunk_act, pad], axis=0)
            prop_list.append(prop[t])
            img_list.append(imgs[t])
            tgt_list.append(chunk_act)
    return (
        np.array(prop_list, dtype=np.float32),
        np.array(img_list, dtype=np.uint8),
        np.array(tgt_list, dtype=np.float32),
    )


def _images_to_batch(imgs_u8: np.ndarray, device: str) -> Tensor:
    """(B,96,96,3) uint8 -> (B,3,96,96) float in [0,1] on device."""
    t = torch.as_tensor(imgs_u8, device=device).float() / 255.0
    return t.permute(0, 3, 1, 2).contiguous()


def train_visuomotor(
    dataset_dir: Path,
    out_path: Path,
    *,
    steps: int = 4000,
    batch: int = 32,
    lr: float = 1e-4,
    chunk: int = 20,
    proprio_noise: float = 0.05,
    image_jitter: float = 0.1,
    seed: int = 0,
) -> Path:
    """Train the visuomotor ACT policy: (front image + proprio) -> action chunk. The privileged
    cube/target xyz are never inputs — the CNN reads them from pixels."""
    torch.manual_seed(seed)
    dataset_dir = Path(dataset_dir)
    stats = json.loads((dataset_dir / "meta" / "stats.json").read_text())
    prop_stats = proprio_stats_from(stats["observation.state"])
    norm = VisuomotorNormalizer(prop_stats, stats["action"])
    device = pick_device()

    prop_np, img_np, tgt_np = _build_visuomotor_samples(dataset_dir, chunk)
    prop = norm.normalize_proprio(torch.as_tensor(prop_np)).to(device)
    tgt = norm.normalize_action(torch.as_tensor(tgt_np)).to(device)

    cfg = VisuomotorACTConfig(chunk=chunk)
    net = VisuomotorACTPolicy(cfg).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=lr)
    rng = np.random.default_rng(seed)
    net.train()
    for _ in range(steps):
        idx = rng.integers(0, len(prop), size=min(batch, len(prop)))
        bi = torch.as_tensor(idx, device=device)
        img_b = _images_to_batch(img_np[idx], device)
        # Light augmentation against covariate shift: proprio noise + global brightness jitter on
        # the image (the cube/target are read from pixels, so robustness to lighting/exposure helps).
        prop_b = prop[bi]
        if proprio_noise > 0:
            prop_b = prop_b + proprio_noise * torch.randn_like(prop_b)
        if image_jitter > 0:
            scale = 1.0 + image_jitter * (2 * torch.rand(img_b.shape[0], 1, 1, 1, device=device) - 1)
            img_b = (img_b * scale).clamp(0.0, 1.0)
        opt.zero_grad()
        loss = torch.nn.functional.l1_loss(net(img_b, prop_b), tgt[bi])
        loss.backward()  # type: ignore[no-untyped-call]
        opt.step()

    out_path = Path(out_path)
    torch.save(
        {
            "state_dict": net.cpu().state_dict(),
            "cfg": vars(cfg),
            "proprio_stats": prop_stats,
            "action_stats": stats["action"],
        },
        out_path,
    )
    return out_path


def train(
    dataset_dir: Path,
    out_path: Path,
    *,
    steps: int = 3000,
    batch: int = 64,
    lr: float = 1e-4,
    chunk: int = 20,
    obs_noise: float = 0.05,
    seed: int = 0,
) -> Path:
    torch.manual_seed(seed)
    dataset_dir = Path(dataset_dir)
    stats = json.loads((dataset_dir / "meta" / "stats.json").read_text())
    norm = Normalizer(stats)
    device = pick_device()

    obs_np, tgt_np = _build_samples(dataset_dir, chunk)
    obs = norm.normalize_obs(torch.as_tensor(obs_np)).to(device)
    tgt = norm.normalize_action(torch.as_tensor(tgt_np)).to(device)

    cfg = ACTConfig(chunk=chunk)
    net = ACTPolicy(cfg).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=lr)
    rng = np.random.default_rng(seed)
    net.train()
    for _ in range(steps):
        idx = rng.integers(0, len(obs), size=min(batch, len(obs)))
        bi = torch.as_tensor(idx, device=device)
        # Observation-noise augmentation (DART-style): perturb the (normalized) obs so the policy
        # learns to recover from the small state errors it will accumulate in closed-loop rollout.
        # This is the main defence against compounding error / covariate shift.
        batch_obs = obs[bi]
        if obs_noise > 0:
            batch_obs = batch_obs + obs_noise * torch.randn_like(batch_obs)
        opt.zero_grad()
        loss = torch.nn.functional.l1_loss(net(batch_obs), tgt[bi])
        loss.backward()  # type: ignore[no-untyped-call]
        opt.step()

    out_path = Path(out_path)
    torch.save(
        {"state_dict": net.cpu().state_dict(), "cfg": vars(cfg), "stats": stats},
        out_path,
    )
    return out_path
