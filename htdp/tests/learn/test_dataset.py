# tests/learn/test_dataset.py
import json

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")

from htdp.learn.dataset import CUBE_REGION, generate_demos, sample_cube_positions


def test_sample_positions_deterministic_and_in_region():
    a = sample_cube_positions(5, seed=0)
    b = sample_cube_positions(5, seed=0)
    assert a == b
    # M2.5 region restricted to the physics teacher's confirmed friction-grasp success zone:
    # the x=0.46 column fails entirely (see docs/m2/a1-physics-grasp.md sweep), so x_lo = 0.48.
    for x, y in a:
        assert 0.48 <= x <= 0.55 and -0.20 <= y <= -0.10


def test_sample_ood_positions_deterministic_disjoint_and_in_ood_band():
    """OOD1: same friction-feasible x-band as CUBE_REGION, but a y-band never sampled in
    training (docs/m2/ood1-generalization-scope.md — y=-0.30 edge fails the grasp per the
    feasibility sweep, so the OOD band is clamped to y in [-0.29, -0.20])."""
    from htdp.learn.dataset import sample_ood_positions

    a = sample_ood_positions(30, seed=0)
    b = sample_ood_positions(30, seed=0)
    assert a == b  # deterministic

    (xlo, xhi), (ylo, yhi) = CUBE_REGION
    for x, y in a:
        assert xlo <= x <= xhi
        assert -0.29 <= y <= -0.20
    assert set(a).isdisjoint(set(sample_cube_positions(30, seed=0)))


def test_generate_demos_writes_lerobot_layout(tmp_path):
    out = generate_demos(tmp_path / "demos", n_train=2, n_test=1, seed=0)

    # parquet episodes exist for the 2 train demos
    eps = sorted((out / "data" / "chunk-000").glob("episode_*.parquet"))
    assert len(eps) == 2

    import polars as pl

    df = pl.read_parquet(eps[0])
    assert set(["observation.state", "action", "timestamp", "frame_index",
                "episode_index", "index"]).issubset(df.columns)
    assert len(df["observation.state"][0]) == 17
    assert len(df["action"][0]) == 8

    info = json.loads((out / "meta" / "info.json").read_text())
    assert info["fps"] == 25
    assert info["features"]["observation.state"]["shape"] == [17]

    stats = json.loads((out / "meta" / "stats.json").read_text())
    assert len(stats["observation.state"]["mean"]) == 17
    assert len(stats["action"]["mean"]) == 8

    # The whole point of the physics teacher: the finger-width feature (index 16) now VARIES.
    # A non-trivial std means it carries grasp information instead of being a constant landmine.
    assert stats["observation.state"]["std"][16] > 0.01

    test_pos = json.loads((out / "meta" / "test_positions.json").read_text())
    assert len(test_pos) == 1


def test_generate_demos_domain_randomize_off_by_default_ignores_dr_seed(tmp_path):
    """DR must be opt-in: passing domain_randomize=False (default) never calls randomize_scene,
    so the existing B1/B2/B3 gates and committed numbers stay reproducible (docs/m2/
    c1-domain-randomization-scope.md risk: "Keep DR default-off")."""
    from unittest.mock import patch

    with patch("htdp.replay.domain_randomization.randomize_scene") as spy:
        generate_demos(tmp_path / "demos", n_train=2, n_test=1, seed=0)
    spy.assert_not_called()


def test_generate_demos_domain_randomize_varies_table_color_across_episodes(tmp_path):
    """With domain_randomize=True, each episode gets an independently randomized scene (per-
    episode seed derived from the base seed), so table/background color differs across episodes
    -- while the red cube stays visible (option A, keeps the B2 red-pixel gate valid)."""
    import numpy as np

    out = generate_demos(
        tmp_path / "demos", n_train=2, n_test=0, seed=0, domain_randomize=True
    )
    data_dir = out / "data" / "chunk-000"
    imgs0 = np.load(data_dir / "episode_000000_image.npy")
    imgs1 = np.load(data_dir / "episode_000001_image.npy")

    # background corner (top-left, away from arm/cube) mean color differs across episodes
    corner0 = imgs0[0, :10, :10].astype(float).mean(axis=(0, 1))
    corner1 = imgs1[0, :10, :10].astype(float).mean(axis=(0, 1))
    assert not np.allclose(corner0, corner1, atol=2.0)

    # red cube still visible (red-pixel gate holds under option-A mild hue jitter)
    for imgs in (imgs0, imgs1):
        r, g, b = imgs[..., 0].astype(int), imgs[..., 1].astype(int), imgs[..., 2].astype(int)
        assert int(np.count_nonzero((r > 120) & (g < 100) & (b < 100))) > 20


def test_generate_demos_writes_aligned_image_sidecar(tmp_path):
    """B2: each episode gets a uint8 image stack [T,96,96,3] aligned 1:1 with its parquet rows.

    Stored as a sidecar .npy (parquet stays low-dim, train.py unchanged); B3 loads it by
    frame_index. The frames must show the red cube -- a zero/blank stack would silently train a
    blind visuomotor policy in B3 (the render-side false-green lesson, carried into the dataset).
    """
    import numpy as np
    import polars as pl

    out = generate_demos(tmp_path / "demos", n_train=2, n_test=1, seed=0)
    data_dir = out / "data" / "chunk-000"

    for ep_parquet in sorted(data_dir.glob("episode_*.parquet")):
        img_path = ep_parquet.with_name(ep_parquet.stem + "_image.npy")
        assert img_path.exists(), f"missing image sidecar for {ep_parquet.name}"
        imgs = np.load(img_path)
        rows = len(pl.read_parquet(ep_parquet))
        assert imgs.shape == (rows, 96, 96, 3)
        assert imgs.dtype == np.uint8
        # red cube present in at least one frame (camera actually captured the workspace)
        r, g, b = imgs[..., 0].astype(int), imgs[..., 1].astype(int), imgs[..., 2].astype(int)
        assert int(np.count_nonzero((r > 120) & (g < 100) & (b < 100))) > 20

    info = json.loads((out / "meta" / "info.json").read_text())
    assert info["features"]["observation.image"]["shape"] == [96, 96, 3]
    assert info["features"]["observation.image"]["dtype"] == "uint8"
