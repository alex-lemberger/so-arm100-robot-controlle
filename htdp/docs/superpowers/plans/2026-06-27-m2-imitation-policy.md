# M2 — Imitation Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train a state-based ACT imitation policy on demos generated from the M1 scripted Franka pick-and-place, then run it autonomously closed-loop in MuJoCo over held-out cube positions and report success-rate vs the scripted-IK baseline.

**Architecture:** A new lazy-imported `htdp.learn` package. The M1 scripted episode is the *teacher*: run it N times with randomized cube positions, recording `(observation.state, action)` per waypoint step into a LeRobotDataset-format directory. A compact ACT transformer (PyTorch/MPS) learns obs→action-chunk. Eval rolls the policy closed-loop through the Franka's position actuators, grasping via the M1 kinematic-attach gated on the policy's gripper command + cube proximity, and compares success-rate against the scripted baseline.

**Tech Stack:** Python 3.11, PyTorch (MPS), numpy, polars (parquet), MuJoCo ≥3.1 (existing `replay` extra), typer.

## Global Constraints

- Python `>=3.11`; `mypy --strict` must pass; `ruff` line-length 100, LF endings.
- New code lives behind a new `learn` optional extra and is **lazy-imported** inside functions; importing `htdp.learn.*` at module load must NOT require torch/mujoco. Raise `LearnUnavailable` with `"install with: uv sync --extra learn"` when a heavy dep is missing.
- Heavy tests gated with `pytest.importorskip("torch")` (and `mujoco`) so the base suite stays green without the extra.
- Determinism: seeded data-gen and eval produce identical results across reruns. MPS *training* is documented as reproducible-enough, not bit-exact.
- Vendored assets already ship via `[tool.hatch.build.targets.wheel].artifacts`; no new asset globs needed.
- Existing `htdp sim-task` / `htdp.replay.*` paths stay working and untouched except the single `episode.py` change in Task 2.
- Observation vector dim = **17**; action vector dim = **8**. These are fixed contract values used by every task.

---

### Task 1: `learn` extra + package skeleton + unavailability guard

**Files:**
- Modify: `pyproject.toml` (add `learn` extra)
- Create: `src/htdp/learn/__init__.py`
- Create: `src/htdp/learn/errors.py`
- Test: `tests/learn/test_package_imports.py`

**Interfaces:**
- Produces:
  - `htdp.learn.errors.LearnUnavailable(RuntimeError)` — raised when torch is missing.
  - `htdp.learn` importable with no heavy deps installed.

- [ ] **Step 1: Add the `learn` extra to pyproject.toml**

In `pyproject.toml`, under `[project.optional-dependencies]`, add this line after the `replay = [...]` line:

```toml
learn = ["torch>=2.2", "mujoco>=3.1", "mink>=1.1", "daqp>=0.5", "numpy>=1.26"]
```

- [ ] **Step 2: Write the failing test**

```python
# tests/learn/test_package_imports.py
def test_learn_imports_without_torch():
    import htdp.learn  # must not import torch at module load
    from htdp.learn.errors import LearnUnavailable

    assert issubclass(LearnUnavailable, RuntimeError)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/learn/test_package_imports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.learn'`

- [ ] **Step 4: Create the package files**

```python
# src/htdp/learn/__init__.py
"""State-based imitation-learning loop (M2): demo generation, ACT policy, training, eval."""
```

```python
# src/htdp/learn/errors.py
from __future__ import annotations


class LearnUnavailable(RuntimeError):
    """Raised when an optional learning dependency (torch) is not installed."""
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --extra dev pytest tests/learn/test_package_imports.py -v`
Expected: PASS

- [ ] **Step 6: Sync the new extra**

Run: `uv sync --extra replay --extra learn --extra dev`
Expected: torch installed; no errors.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/htdp/learn/__init__.py src/htdp/learn/errors.py tests/learn/test_package_imports.py
git commit -m "feat(learn): add learn extra + package skeleton with LearnUnavailable"
```

---

### Task 2: Parametrize the M1 episode (randomized cube + grasp-flag hook)

**Files:**
- Modify: `src/htdp/replay/episode.py`
- Test: `tests/replay/test_episode_cube_xy.py`

**Interfaces:**
- Consumes: existing `run_episode(*, interp=25, settle=6, seed=0, on_step=None) -> EpisodeResult`.
- Produces:
  - `run_episode(*, interp=25, settle=6, seed=0, cube_xy=None, on_step=None) -> EpisodeResult` where `cube_xy: tuple[float, float] | None` overrides the cube's start xy.
  - `on_step` callback signature becomes `on_step(data, frame_index, grasp_active: bool)`.
  - Waypoints are keyed off the *live* cube position (so randomized cubes are picked correctly).

**Context:** Today `_waypoints(model)` reads the compile-time `model.body("cube").pos`. After randomizing the cube we must key waypoints off the actual position. `render.py`'s `on_step` currently takes `(data, step_index)` and must be updated to accept the third arg.

- [ ] **Step 1: Write the failing test**

```python
# tests/replay/test_episode_cube_xy.py
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")

from htdp.replay.episode import run_episode


def test_cube_xy_override_is_picked_and_placed():
    a = run_episode(cube_xy=(0.47, -0.18))
    assert abs(a.object_start_xy[0] - 0.47) < 1e-6
    assert abs(a.object_start_xy[1] - (-0.18)) < 1e-6
    assert a.place_error < 0.05  # still placed at the (fixed) target
    assert a.grasp_dist < 0.02   # gripper really on the (moved) cube

    # grasp flag is delivered to on_step at least once
    seen = []
    run_episode(cube_xy=(0.47, -0.18), on_step=lambda d, f, g: seen.append(g))
    assert any(seen) and not all(seen)  # grasp toggles on then off
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra replay pytest tests/replay/test_episode_cube_xy.py -v`
Expected: FAIL — `run_episode() got an unexpected keyword argument 'cube_xy'`

- [ ] **Step 3: Update `_waypoints` to take an explicit cube position**

In `src/htdp/replay/episode.py`, replace the `_waypoints` function:

```python
def _waypoints(cube, tgt):  # type: ignore[no-untyped-def]
    # Cartesian path keyed off the live cube + target positions; (x, y, z, grasp_active).
    return [
        (cube[0], cube[1], _Z_HI, False),  # approach above cube
        (cube[0], cube[1], _Z_LO, False),  # descend to cube
        (cube[0], cube[1], _Z_LO, True),  # grasp (attach on)
        (cube[0], cube[1], _Z_HI, True),  # lift
        (tgt[0], tgt[1], _Z_HI, True),  # traverse to target
        (tgt[0], tgt[1], _Z_LO, True),  # descend to target
        (tgt[0], tgt[1], _Z_LO, False),  # release (attach off)
        (tgt[0], tgt[1], _Z_HI, False),  # retreat
    ]
```

- [ ] **Step 4: Add `cube_xy` handling + grasp-flag hook in `run_episode`**

In `run_episode`, change the signature line to:

```python
def run_episode(*, interp: int = 25, settle: int = 6, seed: int = 0, cube_xy=None, on_step=None) -> EpisodeResult:  # type: ignore[no-untyped-def]
```

Immediately after `mujoco.mj_forward(model, data)` (the first one, after creating `data`), insert the cube override:

```python
    if cube_xy is not None:
        data.qpos[cube_qadr : cube_qadr + 2] = cube_xy
        mujoco.mj_forward(model, data)
```

(Move the `cube_qadr` / `cube_vadr` computation above this block if needed so they are defined first.)

Replace the `waypoints = _waypoints(model)` line with:

```python
    cube_pos = data.body(OBJECT_BODY).xpos.copy()
    tgt_pos = model.site(TARGET_SITE).pos
    waypoints = _waypoints(cube_pos, tgt_pos)  # type: ignore[no-untyped-call]
```

Find the `on_step` invocation inside the step loop and change it to pass the grasp flag:

```python
            if on_step is not None:
                on_step(data, frames, grasp)
```

- [ ] **Step 5: Update `render.py`'s on_step to accept the third arg**

In `src/htdp/replay/render.py`, change the `on_step` definition:

```python
    def on_step(data, step_index, grasp_active):  # type: ignore[no-untyped-def]
        if step_index % every == 0:
            renderer.update_scene(data)
            frames.append(renderer.render())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run --extra replay pytest tests/replay/test_episode_cube_xy.py tests/replay/test_episode.py tests/replay/test_render.py -v`
Expected: PASS (3 files)

- [ ] **Step 7: Commit**

```bash
git add src/htdp/replay/episode.py src/htdp/replay/render.py tests/replay/test_episode_cube_xy.py
git commit -m "feat(replay): randomized cube_xy + grasp-flag on_step hook for M2 teacher"
```

---

### Task 3: `learn/obs.py` — observation + action contract

**Files:**
- Create: `src/htdp/learn/obs.py`
- Test: `tests/learn/test_obs.py`

**Interfaces:**
- Produces:
  - `OBS_DIM = 17`, `ACTION_DIM = 8`
  - `OBS_NAMES: list[str]` (len 17), `ACTION_NAMES: list[str]` (len 8)
  - `build_observation(model, data, grasp_sid: int) -> np.ndarray` shape `(17,)`: `[q0..q6, finger_width, eef_x,eef_y,eef_z, cube_x,cube_y,cube_z, tgt_x,tgt_y,tgt_z]`.
  - `build_action(data, grasp_active: bool) -> np.ndarray` shape `(8,)`: `[q0..q6, gripper]` where gripper = 1.0 if grasp_active else 0.0.

**Context:** This is the single source of truth shared by data-gen (Task 4) and rollout (Task 7). MuJoCo state layout for the task scene: `data.qpos[0:7]` = arm joints, `data.qpos[7]` = finger_joint1. The grasp site id comes from `mujoco.mj_name2id(model, mjOBJ_SITE, "grasp_site")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/learn/test_obs.py
import pytest

pytest.importorskip("mujoco")

import numpy as np

from htdp.learn.obs import ACTION_DIM, OBS_DIM, build_action, build_observation


def test_obs_and_action_shapes_and_target():
    import mujoco

    from htdp.replay.scene import TASK_SCENE_XML, TARGET_SITE

    m = mujoco.MjModel.from_xml_path(str(TASK_SCENE_XML))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    gsid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "grasp_site")

    obs = build_observation(m, d, gsid)
    assert obs.shape == (OBS_DIM,)
    # last three entries are the fixed target xyz
    tgt = m.site(TARGET_SITE).pos
    assert np.allclose(obs[14:17], tgt)

    act_open = build_action(d, False)
    act_closed = build_action(d, True)
    assert act_open.shape == (ACTION_DIM,)
    assert act_open[7] == 0.0 and act_closed[7] == 1.0
    assert np.allclose(act_open[:7], d.qpos[:7])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra learn pytest tests/learn/test_obs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.learn.obs'`

- [ ] **Step 3: Write `obs.py`**

```python
# src/htdp/learn/obs.py
from __future__ import annotations

import numpy as np

OBS_DIM = 17
ACTION_DIM = 8

OBS_NAMES = [
    *(f"q{i}" for i in range(7)),
    "finger_width",
    "eef_x", "eef_y", "eef_z",
    "cube_x", "cube_y", "cube_z",
    "tgt_x", "tgt_y", "tgt_z",
]
ACTION_NAMES = [*(f"q{i}_target" for i in range(7)), "gripper"]


def build_observation(model, data, grasp_sid: int) -> np.ndarray:  # type: ignore[no-untyped-def]
    """State observation, shape (17,). See OBS_NAMES for the layout."""
    eef = data.site_xpos[grasp_sid]
    cube = data.body("cube").xpos
    tgt = model.site("target").pos
    return np.concatenate(
        [
            data.qpos[:7],
            data.qpos[7:8],  # finger_joint1 ~ half the gripper width
            eef,
            cube,
            tgt,
        ]
    ).astype(np.float32)


def build_action(data, grasp_active: bool) -> np.ndarray:  # type: ignore[no-untyped-def]
    """Action, shape (8,): 7 joint position targets + gripper (1=close, 0=open)."""
    return np.concatenate(
        [data.qpos[:7], np.array([1.0 if grasp_active else 0.0])]
    ).astype(np.float32)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra learn pytest tests/learn/test_obs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/htdp/learn/obs.py tests/learn/test_obs.py
git commit -m "feat(learn): obs/action contract shared by data-gen and rollout"
```

---

### Task 4: `learn/dataset.py` — generate LeRobotDataset-format demos

**Files:**
- Create: `src/htdp/learn/dataset.py`
- Test: `tests/learn/test_dataset.py`

**Interfaces:**
- Consumes: `run_episode` (Task 2), `build_observation`/`build_action`/`OBS_NAMES`/`ACTION_NAMES`/`OBS_DIM`/`ACTION_DIM` (Task 3).
- Produces:
  - `CUBE_REGION = ((0.45, 0.55), (-0.20, -0.10))` — ((x_lo,x_hi),(y_lo,y_hi)).
  - `sample_cube_positions(n: int, seed: int) -> list[tuple[float, float]]`.
  - `generate_demos(out_dir: Path, *, n_train: int = 100, n_test: int = 25, seed: int = 0, fps: int = 25) -> Path` — writes the dataset and returns `out_dir`. Test positions written to `out_dir/meta/test_positions.json`.
  - On-disk layout: `data/chunk-000/episode_XXXXXX.parquet`, `meta/info.json`, `meta/episodes.jsonl`, `meta/stats.json`, `meta/test_positions.json`.

**Context:** Record one `(obs, action)` per *waypoint step*, i.e. only on the last settle sub-step (`frame % settle == settle - 1`). The episode uses `interp=25`, 8 waypoints → 200 records/episode. Parquet columns: `observation.state` (list[float] len 17), `action` (list[float] len 8), `timestamp` (float, frame_index/fps), `frame_index` (int), `episode_index` (int), `index` (int global). Stats are per-feature mean/std/min/max over the train split, stored as nested dicts under `observation.state` and `action`.

- [ ] **Step 1: Write the failing test**

```python
# tests/learn/test_dataset.py
import json

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")

from htdp.learn.dataset import generate_demos, sample_cube_positions


def test_sample_positions_deterministic_and_in_region():
    a = sample_cube_positions(5, seed=0)
    b = sample_cube_positions(5, seed=0)
    assert a == b
    for x, y in a:
        assert 0.45 <= x <= 0.55 and -0.20 <= y <= -0.10


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

    test_pos = json.loads((out / "meta" / "test_positions.json").read_text())
    assert len(test_pos) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra learn pytest tests/learn/test_dataset.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.learn.dataset'`

- [ ] **Step 3: Write `dataset.py`**

```python
# src/htdp/learn/dataset.py
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from htdp.learn.obs import (
    ACTION_DIM,
    ACTION_NAMES,
    OBS_DIM,
    OBS_NAMES,
    build_action,
    build_observation,
)

CUBE_REGION = ((0.45, 0.55), (-0.20, -0.10))  # ((x_lo, x_hi), (y_lo, y_hi))
_SETTLE = 6
_TASK = "pick the cube and place it on the target"


def sample_cube_positions(n: int, seed: int) -> list[tuple[float, float]]:
    rng = np.random.default_rng(seed)
    (xlo, xhi), (ylo, yhi) = CUBE_REGION
    xs = rng.uniform(xlo, xhi, n)
    ys = rng.uniform(ylo, yhi, n)
    return [(float(x), float(y)) for x, y in zip(xs, ys)]


def _record_episode(cube_xy, ep_index, index_start):  # type: ignore[no-untyped-def]
    """Run the scripted teacher once; return (rows, n_frames). One row per waypoint step."""
    import mujoco

    from htdp.replay.episode import run_episode
    from htdp.replay.scene import TASK_SCENE_XML

    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_XML))
    grasp_sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "grasp_site")

    rows: list[dict] = []

    def on_step(data, frame, grasp):  # type: ignore[no-untyped-def]
        if frame % _SETTLE != _SETTLE - 1:
            return
        fi = len(rows)
        rows.append(
            {
                "observation.state": build_observation(model, data, grasp_sid).tolist(),
                "action": build_action(data, grasp).tolist(),
                "timestamp": fi / 25.0,
                "frame_index": fi,
                "episode_index": ep_index,
                "index": index_start + fi,
            }
        )

    # Re-run with the SAME model instance so site ids match: run_episode builds its own
    # model internally, but ids for the shared scene file are identical, so reuse is safe.
    run_episode(cube_xy=cube_xy, on_step=on_step)
    return rows


def _feature_stats(values: np.ndarray) -> dict:
    return {
        "mean": values.mean(0).tolist(),
        "std": (values.std(0) + 1e-6).tolist(),
        "min": values.min(0).tolist(),
        "max": values.max(0).tolist(),
    }


def generate_demos(
    out_dir: Path,
    *,
    n_train: int = 100,
    n_test: int = 25,
    seed: int = 0,
    fps: int = 25,
) -> Path:
    out_dir = Path(out_dir)
    data_dir = out_dir / "data" / "chunk-000"
    meta_dir = out_dir / "meta"
    data_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    train_pos = sample_cube_positions(n_train, seed)
    test_pos = sample_cube_positions(n_test, seed + 1000)

    episodes_meta = []
    all_obs: list[list[float]] = []
    all_act: list[list[float]] = []
    index = 0
    for ep, cube_xy in enumerate(train_pos):
        rows = _record_episode(cube_xy, ep, index)
        index += len(rows)
        pl.DataFrame(rows).write_parquet(data_dir / f"episode_{ep:06d}.parquet")
        episodes_meta.append({"episode_index": ep, "length": len(rows), "task": _TASK})
        all_obs.extend(r["observation.state"] for r in rows)
        all_act.extend(r["action"] for r in rows)

    info = {
        "codebase_version": "v2.0",
        "fps": fps,
        "robot_type": "franka_panda",
        "total_episodes": n_train,
        "total_frames": index,
        "features": {
            "observation.state": {"dtype": "float32", "shape": [OBS_DIM], "names": OBS_NAMES},
            "action": {"dtype": "float32", "shape": [ACTION_DIM], "names": ACTION_NAMES},
        },
    }
    (meta_dir / "info.json").write_text(json.dumps(info, indent=2))
    with (meta_dir / "episodes.jsonl").open("w") as fh:
        for em in episodes_meta:
            fh.write(json.dumps(em) + "\n")
    stats = {
        "observation.state": _feature_stats(np.array(all_obs, dtype=np.float32)),
        "action": _feature_stats(np.array(all_act, dtype=np.float32)),
    }
    (meta_dir / "stats.json").write_text(json.dumps(stats, indent=2))
    (meta_dir / "test_positions.json").write_text(json.dumps(test_pos))
    return out_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra learn pytest tests/learn/test_dataset.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/htdp/learn/dataset.py tests/learn/test_dataset.py
git commit -m "feat(learn): generate randomized demos in LeRobotDataset format"
```

---

### Task 5: `learn/policy.py` — compact ACT policy

**Files:**
- Create: `src/htdp/learn/policy.py`
- Test: `tests/learn/test_policy.py`

**Interfaces:**
- Consumes: `OBS_DIM`, `ACTION_DIM` (Task 3).
- Produces:
  - `ACTConfig` dataclass: `obs_dim=17, action_dim=8, chunk=20, hidden=256, heads=4, layers=2`.
  - `ACTPolicy(nn.Module)` with `forward(obs: Tensor[B, obs_dim]) -> Tensor[B, chunk, action_dim]`.
  - `ACTPolicy.act(obs: Tensor[obs_dim]) -> Tensor[chunk, action_dim]` (no-grad single-obs inference).

**Context:** Deterministic chunking transformer (CVAE deferred). Embed obs → repeat as encoder memory; `chunk` learned query tokens attend via a TransformerDecoder; linear head → actions. Keep it tiny.

- [ ] **Step 1: Write the failing test**

```python
# tests/learn/test_policy.py
import pytest

torch = pytest.importorskip("torch")

from htdp.learn.policy import ACTConfig, ACTPolicy


def test_forward_and_act_shapes():
    cfg = ACTConfig()
    net = ACTPolicy(cfg)
    out = net(torch.zeros(4, cfg.obs_dim))
    assert out.shape == (4, cfg.chunk, cfg.action_dim)

    single = net.act(torch.zeros(cfg.obs_dim))
    assert single.shape == (cfg.chunk, cfg.action_dim)


def test_overfit_one_batch_loss_drops():
    torch.manual_seed(0)
    cfg = ACTConfig(chunk=4, hidden=64, layers=1)
    net = ACTPolicy(cfg)
    obs = torch.randn(8, cfg.obs_dim)
    target = torch.randn(8, cfg.chunk, cfg.action_dim)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3)
    first = last = None
    for i in range(100):
        opt.zero_grad()
        loss = torch.nn.functional.l1_loss(net(obs), target)
        loss.backward()
        opt.step()
        if i == 0:
            first = loss.item()
        last = loss.item()
    assert last < first * 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra learn pytest tests/learn/test_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.learn.policy'`

- [ ] **Step 3: Write `policy.py`**

```python
# src/htdp/learn/policy.py
from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn

from htdp.learn.obs import ACTION_DIM, OBS_DIM


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
        return self.head(dec)  # (B, chunk, action_dim)

    @torch.no_grad()
    def act(self, obs: Tensor) -> Tensor:
        self.eval()
        return self.forward(obs.unsqueeze(0)).squeeze(0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra learn pytest tests/learn/test_policy.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/learn/policy.py tests/learn/test_policy.py
git commit -m "feat(learn): compact action-chunking transformer (ACT) policy"
```

---

### Task 6: `learn/train.py` — MPS training loop + checkpoint

**Files:**
- Create: `src/htdp/learn/train.py`
- Test: `tests/learn/test_train.py`

**Interfaces:**
- Consumes: `generate_demos` (Task 4), `ACTConfig`/`ACTPolicy` (Task 5), `LearnUnavailable` (Task 1).
- Produces:
  - `pick_device() -> str` — "mps" if available else "cpu".
  - `Normalizer` with `normalize_obs`, `normalize_action`, `denormalize_action` (numpy-stats based, torch tensors in/out) loaded from `stats.json`.
  - `train(dataset_dir: Path, out_path: Path, *, steps: int = 3000, batch: int = 64, lr: float = 1e-4, chunk: int = 20, seed: int = 0) -> Path` — writes a checkpoint dict (`{"state_dict", "cfg", "stats"}`) to `out_path` and returns it.

**Context:** Load all train parquet episodes into memory. Build chunked samples: for each frame `t` in an episode, target = actions `[t : t+chunk]` padded by repeating the last action; input = obs at `t`. Normalize obs+action with stats. L1 loss. The checkpoint bundles the stats so rollout can denormalize identically.

- [ ] **Step 1: Write the failing test**

```python
# tests/learn/test_train.py
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("mujoco")
pytest.importorskip("mink")

from htdp.learn.dataset import generate_demos
from htdp.learn.train import train


def test_train_writes_checkpoint(tmp_path):
    ds = generate_demos(tmp_path / "demos", n_train=2, n_test=1, seed=0)
    ckpt_path = train(ds, tmp_path / "policy.pt", steps=50, batch=16, chunk=8, seed=0)
    assert ckpt_path.exists()
    ckpt = torch.load(ckpt_path, weights_only=False)
    assert "state_dict" in ckpt and "cfg" in ckpt and "stats" in ckpt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra learn pytest tests/learn/test_train.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.learn.train'`

- [ ] **Step 3: Write `train.py`**

```python
# src/htdp/learn/train.py
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
import torch
from torch import Tensor

from htdp.learn.policy import ACTConfig, ACTPolicy


def pick_device() -> str:
    return "mps" if torch.backends.mps.is_available() else "cpu"


class Normalizer:
    def __init__(self, stats: dict) -> None:
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


def train(
    dataset_dir: Path,
    out_path: Path,
    *,
    steps: int = 3000,
    batch: int = 64,
    lr: float = 1e-4,
    chunk: int = 20,
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
        opt.zero_grad()
        loss = torch.nn.functional.l1_loss(net(obs[bi]), tgt[bi])
        loss.backward()
        opt.step()

    out_path = Path(out_path)
    torch.save(
        {"state_dict": net.cpu().state_dict(), "cfg": vars(cfg), "stats": stats},
        out_path,
    )
    return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra learn pytest tests/learn/test_train.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/htdp/learn/train.py tests/learn/test_train.py
git commit -m "feat(learn): MPS training loop with normalization + bundled checkpoint"
```

---

### Task 7: `learn/rollout.py` — closed-loop actuator rollout + grasp gating

**Files:**
- Create: `src/htdp/learn/rollout.py`
- Test: `tests/learn/test_rollout.py`

**Interfaces:**
- Consumes: `ACTConfig`/`ACTPolicy` (Task 5), `Normalizer`/`pick_device` (Task 6), `build_observation` (Task 3).
- Produces:
  - `@dataclass RolloutResult`: `success: bool`, `place_error: float`, `lifted: bool`, `cube_final_xy: tuple[float, float]`, `steps: int`.
  - `load_policy(ckpt_path: Path)` -> `(ACTPolicy, Normalizer)`.
  - `rollout_policy(policy, normalizer, cube_xy, *, settle: int = 6, max_chunks: int = 40, grasp_thresh: float = 0.03) -> RolloutResult`.

**Context:** Build the task scene; set cube xy via the `cube_free` joint qpos; init arm to the home keyframe (`mj_name2id(... mjOBJ_KEY, "home")` does not exist in the task scene — instead set `data.qpos[:7]` from `htdp.replay.franka.home_qpos()[:7]`). Loop: build+normalize obs → `policy.act` → denormalize → for each action in the chunk: set `data.ctrl[:7] = clip(joint targets, ctrlrange)`, `data.ctrl[7] = 255.0 * (1.0 - gripper)` (gripper 1=close→ctrl 0), `mj_step` `settle` times. Grasp gating: keep an `attached` flag + captured offset; when `gripper > 0.5` and `dist(grasp_site, cube) < grasp_thresh` → attach (slave cube qpos to `grasp_site` + offset, like M1); when `gripper <= 0.5` → release. Track max cube z (lifted if it exceeds start_z + 0.05). Success = cube within 3 cm of target xy AND lifted. Target xy and ids read from the model.

- [ ] **Step 1: Write the failing test**

```python
# tests/learn/test_rollout.py
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("mujoco")
pytest.importorskip("mink")

from htdp.learn.policy import ACTConfig, ACTPolicy
from htdp.learn.rollout import RolloutResult, rollout_policy
from htdp.learn.train import Normalizer


def _dummy_norm():
    stats = {
        "observation.state": {"mean": [0.0] * 17, "std": [1.0] * 17,
                              "min": [0.0] * 17, "max": [1.0] * 17},
        "action": {"mean": [0.0] * 8, "std": [1.0] * 8,
                   "min": [0.0] * 8, "max": [1.0] * 8},
    }
    return Normalizer(stats)


def test_rollout_untrained_policy_runs_without_crashing():
    torch.manual_seed(0)
    net = ACTPolicy(ACTConfig(chunk=8))
    res = rollout_policy(net, _dummy_norm(), (0.50, -0.15), max_chunks=5)
    assert isinstance(res, RolloutResult)
    assert isinstance(res.success, bool)
    assert res.steps > 0


def test_rollout_is_deterministic():
    torch.manual_seed(0)
    net = ACTPolicy(ACTConfig(chunk=8))
    a = rollout_policy(net, _dummy_norm(), (0.50, -0.15), max_chunks=5)
    b = rollout_policy(net, _dummy_norm(), (0.50, -0.15), max_chunks=5)
    assert a.cube_final_xy == b.cube_final_xy
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra learn pytest tests/learn/test_rollout.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.learn.rollout'`

- [ ] **Step 3: Write `rollout.py`**

```python
# src/htdp/learn/rollout.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from htdp.learn.obs import build_observation
from htdp.learn.policy import ACTConfig, ACTPolicy
from htdp.learn.train import Normalizer


@dataclass
class RolloutResult:
    success: bool
    place_error: float
    lifted: bool
    cube_final_xy: tuple[float, float]
    steps: int


def load_policy(ckpt_path: Path):  # type: ignore[no-untyped-def]
    ckpt = torch.load(Path(ckpt_path), weights_only=False)
    cfg = ACTConfig(**ckpt["cfg"])
    net = ACTPolicy(cfg)
    net.load_state_dict(ckpt["state_dict"])
    net.eval()
    return net, Normalizer(ckpt["stats"])


def rollout_policy(
    policy: ACTPolicy,
    normalizer: Normalizer,
    cube_xy,
    *,
    settle: int = 6,
    max_chunks: int = 40,
    grasp_thresh: float = 0.03,
):  # type: ignore[no-untyped-def]
    import mujoco

    from htdp.replay.franka import home_qpos
    from htdp.replay.scene import OBJECT_FREEJOINT, TARGET_SITE, TASK_SCENE_XML

    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_XML))
    data = mujoco.MjData(model)
    grasp_sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "grasp_site")
    cube_jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, OBJECT_FREEJOINT)
    cube_qadr = int(model.jnt_qposadr[cube_jid])
    cube_vadr = int(model.jnt_dofadr[cube_jid])
    tgt = model.site(TARGET_SITE).pos

    data.qpos[:7] = home_qpos()[:7]
    data.qpos[cube_qadr : cube_qadr + 2] = cube_xy
    mujoco.mj_forward(model, data)
    ctrl_lo = model.actuator_ctrlrange[:7, 0]
    ctrl_hi = model.actuator_ctrlrange[:7, 1]
    start_z = float(data.body("cube").xpos[2])

    attached = {"on": False, "offset": None}
    lifted = False
    steps = 0
    for _ in range(max_chunks):
        obs = build_observation(model, data, grasp_sid)
        obs_t = normalizer.normalize_obs(torch.as_tensor(obs))
        chunk = normalizer.denormalize_action(policy.act(obs_t)).numpy()
        for action in chunk:
            data.ctrl[:7] = np.clip(action[:7], ctrl_lo, ctrl_hi)
            gripper = float(action[7])
            data.ctrl[7] = 255.0 * (1.0 - min(max(gripper, 0.0), 1.0))
            for _ in range(settle):
                mujoco.mj_forward(model, data)
                if gripper > 0.5 and not attached["on"]:
                    gap = data.body("cube").xpos - data.site_xpos[grasp_sid]
                    if float(np.linalg.norm(gap)) < grasp_thresh:
                        attached["on"] = True
                        attached["offset"] = gap.copy()
                if gripper <= 0.5:
                    attached["on"] = False
                if attached["on"]:
                    data.qpos[cube_qadr : cube_qadr + 3] = (
                        data.site_xpos[grasp_sid] + attached["offset"]
                    )
                    data.qpos[cube_qadr + 3 : cube_qadr + 7] = (1.0, 0.0, 0.0, 0.0)
                    data.qvel[cube_vadr : cube_vadr + 6] = 0.0
                mujoco.mj_step(model, data)
                steps += 1
                if float(data.body("cube").xpos[2]) > start_z + 0.05:
                    lifted = True

    cube = data.body("cube").xpos
    place_error = float(np.hypot(cube[0] - tgt[0], cube[1] - tgt[1]))
    success = bool(place_error < 0.03 and lifted)
    return RolloutResult(success, place_error, lifted, (float(cube[0]), float(cube[1])), steps)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra learn pytest tests/learn/test_rollout.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/learn/rollout.py tests/learn/test_rollout.py
git commit -m "feat(learn): closed-loop actuator rollout with policy-gated grasp"
```

---

### Task 8: `learn/eval.py` — policy vs scripted baseline report

**Files:**
- Create: `src/htdp/learn/eval.py`
- Test: `tests/learn/test_eval.py`

**Interfaces:**
- Consumes: `load_policy`/`rollout_policy`/`RolloutResult` (Task 7), `run_episode` (Task 2).
- Produces:
  - `baseline_at(positions) -> dict` — runs scripted `run_episode` per position; returns `{"success_rate", "mean_place_error", "n"}` (success = place_error < 0.03).
  - `evaluate(ckpt_path: Path, positions, *, out_path: Path | None = None) -> dict` — returns `{"policy": {...}, "baseline": {...}}`; writes JSON if `out_path` given.

**Context:** Reuse the test positions written by `generate_demos` (`meta/test_positions.json`). The baseline runs the scripted teacher (always ~100%); the policy runs `rollout_policy`. Aggregate success-rate and mean place-error for both.

- [ ] **Step 1: Write the failing test**

```python
# tests/learn/test_eval.py
import json

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("mujoco")
pytest.importorskip("mink")

from htdp.learn.dataset import generate_demos
from htdp.learn.eval import baseline_at, evaluate
from htdp.learn.train import train


def test_baseline_succeeds(tmp_path):
    rep = baseline_at([(0.50, -0.15), (0.48, -0.12)])
    assert rep["n"] == 2
    assert rep["success_rate"] == 1.0  # scripted teacher always places


def test_evaluate_end_to_end_smoke(tmp_path):
    ds = generate_demos(tmp_path / "demos", n_train=2, n_test=2, seed=0)
    ckpt = train(ds, tmp_path / "policy.pt", steps=50, batch=16, chunk=8, seed=0)
    positions = json.loads((ds / "meta" / "test_positions.json").read_text())
    rep = evaluate(ckpt, [tuple(p) for p in positions], out_path=tmp_path / "report.json")
    assert set(rep) == {"policy", "baseline"}
    assert "success_rate" in rep["policy"] and "success_rate" in rep["baseline"]
    assert (tmp_path / "report.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra learn pytest tests/learn/test_eval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.learn.eval'`

- [ ] **Step 3: Write `eval.py`**

```python
# src/htdp/learn/eval.py
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from htdp.learn.rollout import load_policy, rollout_policy


def baseline_at(positions) -> dict:  # type: ignore[no-untyped-def]
    from htdp.replay.episode import run_episode

    errs = []
    succ = 0
    for cube_xy in positions:
        r = run_episode(cube_xy=tuple(cube_xy))
        errs.append(r.place_error)
        succ += int(r.place_error < 0.03)
    n = len(positions)
    return {
        "success_rate": succ / n if n else 0.0,
        "mean_place_error": float(np.mean(errs)) if errs else 0.0,
        "n": n,
    }


def _policy_at(ckpt_path: Path, positions) -> dict:  # type: ignore[no-untyped-def]
    net, norm = load_policy(ckpt_path)
    errs = []
    succ = 0
    for cube_xy in positions:
        r = rollout_policy(net, norm, tuple(cube_xy))
        errs.append(r.place_error)
        succ += int(r.success)
    n = len(positions)
    return {
        "success_rate": succ / n if n else 0.0,
        "mean_place_error": float(np.mean(errs)) if errs else 0.0,
        "n": n,
    }


def evaluate(ckpt_path: Path, positions, *, out_path: Path | None = None) -> dict:  # type: ignore[no-untyped-def]
    report = {"policy": _policy_at(ckpt_path, positions), "baseline": baseline_at(positions)}
    if out_path is not None:
        Path(out_path).write_text(json.dumps(report, indent=2))
    return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra learn pytest tests/learn/test_eval.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/learn/eval.py tests/learn/test_eval.py
git commit -m "feat(learn): policy-vs-baseline success-rate evaluation report"
```

---

### Task 9: CLI commands (`gen-demos`, `train-policy`, `eval-policy`)

**Files:**
- Modify: `src/htdp/cli.py`
- Test: `tests/test_cli_learn.py`

**Interfaces:**
- Consumes: `generate_demos` (Task 4), `train` (Task 6), `evaluate` (Task 8), `LearnUnavailable` (Task 1).
- Produces three typer commands:
  - `htdp gen-demos --out DIR [--n-train 100] [--n-test 25] [--seed 0]`
  - `htdp train-policy --demos DIR --out policy.pt [--steps 3000]`
  - `htdp eval-policy --demos DIR --policy policy.pt [--out report.json]` (reads `meta/test_positions.json`)

**Context:** Follow the existing `sim_task` command pattern in `cli.py` (lazy imports inside the function, `typer.echo` for output). Wrap heavy imports so a missing extra prints a clear error and exits 1.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_learn.py
import json

import pytest

pytest.importorskip("torch")
pytest.importorskip("mujoco")
pytest.importorskip("mink")

from typer.testing import CliRunner

from htdp.cli import app

runner = CliRunner()


def test_cli_gen_train_eval(tmp_path):
    demos = tmp_path / "demos"
    r1 = runner.invoke(app, ["gen-demos", "--out", str(demos),
                             "--n-train", "2", "--n-test", "2", "--seed", "0"])
    assert r1.exit_code == 0, r1.output
    assert (demos / "meta" / "info.json").exists()

    policy = tmp_path / "policy.pt"
    r2 = runner.invoke(app, ["train-policy", "--demos", str(demos),
                             "--out", str(policy), "--steps", "20"])
    assert r2.exit_code == 0, r2.output
    assert policy.exists()

    report = tmp_path / "report.json"
    r3 = runner.invoke(app, ["eval-policy", "--demos", str(demos),
                             "--policy", str(policy), "--out", str(report)])
    assert r3.exit_code == 0, r3.output
    assert report.exists()
    rep = json.loads(report.read_text())
    assert "policy" in rep and "baseline" in rep
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra learn pytest tests/test_cli_learn.py -v`
Expected: FAIL — `Error: No such command 'gen-demos'`

- [ ] **Step 3: Add the commands to `cli.py`**

Append these three commands near the `sim_task` command in `src/htdp/cli.py`:

```python
@app.command(name="gen-demos")
def gen_demos(
    out: Path = typer.Option(..., "--out", help="dataset output directory"),
    n_train: int = typer.Option(100, "--n-train"),
    n_test: int = typer.Option(25, "--n-test"),
    seed: int = typer.Option(0, "--seed"),
) -> None:
    """Generate randomized scripted pick-place demos in LeRobotDataset format."""
    from htdp.learn.dataset import generate_demos

    generate_demos(out, n_train=n_train, n_test=n_test, seed=seed)
    typer.echo(f"wrote demos to {out} (train={n_train} test={n_test})")


@app.command(name="train-policy")
def train_policy(
    demos: Path = typer.Option(..., "--demos", help="dataset directory from gen-demos"),
    out: Path = typer.Option(..., "--out", help="checkpoint path (policy.pt)"),
    steps: int = typer.Option(3000, "--steps"),
) -> None:
    """Train the ACT imitation policy on generated demos."""
    from htdp.learn.train import pick_device, train

    train(demos, out, steps=steps)
    typer.echo(f"trained on {pick_device()}; wrote {out}")


@app.command(name="eval-policy")
def eval_policy(
    demos: Path = typer.Option(..., "--demos", help="dataset dir (for test_positions.json)"),
    policy: Path = typer.Option(..., "--policy", help="checkpoint path"),
    out: Path = typer.Option(None, "--out", help="optional report JSON path"),
) -> None:
    """Roll out the policy on held-out positions; report success-rate vs scripted baseline."""
    import json

    from htdp.learn.eval import evaluate

    positions = [tuple(p) for p in json.loads((demos / "meta" / "test_positions.json").read_text())]
    report = evaluate(policy, positions, out_path=out)
    p, b = report["policy"], report["baseline"]
    typer.echo(
        f"policy: success={p['success_rate']:.2f} place_err={p['mean_place_error']:.4f} | "
        f"baseline: success={b['success_rate']:.2f} place_err={b['mean_place_error']:.4f}"
    )
```

Ensure `from pathlib import Path` and `import typer` are already imported at the top of `cli.py` (they are, used by existing commands).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra learn pytest tests/test_cli_learn.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/htdp/cli.py tests/test_cli_learn.py
git commit -m "feat(cli): gen-demos, train-policy, eval-policy commands for M2"
```

---

### Task 10: Full M2 run + docs

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: all prior tasks.

**Context:** Generate the real dataset, train for real, eval, and record the headline number. Then document M2.

- [ ] **Step 1: Generate the full dataset**

Run: `uv run --extra learn htdp gen-demos --out demos --n-train 100 --n-test 25 --seed 0`
Expected: `wrote demos to demos (train=100 test=25)`; `demos/meta/info.json` exists.

- [ ] **Step 2: Train the policy**

Run: `uv run --extra learn htdp train-policy --demos demos --out policy.pt --steps 3000`
Expected: `trained on mps; wrote policy.pt` (cpu acceptable); `policy.pt` exists.

- [ ] **Step 3: Evaluate vs baseline**

Run: `uv run --extra learn htdp eval-policy --demos demos --policy policy.pt --out docs/demo/m2_eval.json`
Expected: prints policy + baseline success/place_err. **Acceptance: policy success_rate ≥ 0.80.** If below, increase `--steps` (e.g. 6000), then re-eval. If still below after 6000 steps, STOP and report the number — do not silently accept; the spec bar is 80%.

- [ ] **Step 4: Run the full gate**

Run: `uv run --extra replay --extra learn --extra dev pytest -q && uv run --extra dev ruff check src/htdp tests && uv run --extra dev --extra learn --extra replay mypy --strict src/htdp/learn`
Expected: all pass / clean.

- [ ] **Step 5: Update ROADMAP.md**

In `docs/ROADMAP.md`, add an "M2 — done" entry below the M1 entry:

```markdown
**M2 — done:** state-based imitation. `htdp gen-demos` records randomized scripted
pick-place demos (LeRobotDataset format); `htdp train-policy` trains a compact ACT
transformer (PyTorch/MPS); `htdp eval-policy` runs the policy closed-loop through the
Franka's position actuators over held-out cube positions and reports success-rate vs the
scripted-IK baseline (`docs/demo/m2_eval.json`). Grasp is the M1 kinematic attach, gated on
the policy's gripper action. Pixels/visuomotor deferred to M2.5.
```

- [ ] **Step 6: Update README.md**

In `README.md`, after the M1 teleop-replay section, add:

```markdown
## Imitation policy (M2)

`htdp gen-demos` → `htdp train-policy` → `htdp eval-policy`: a compact ACT policy is trained
on scripted demonstrations and then drives the Franka **autonomously closed-loop** in MuJoCo,
generalizing to unseen cube positions. Success-rate is reported against the scripted-IK
baseline. State-based observations (joint + object poses); visuomotor (pixels) is the M2.5
extension.
```

- [ ] **Step 7: Commit**

```bash
git add docs/ROADMAP.md README.md docs/demo/m2_eval.json
git commit -m "docs(m2): record imitation-policy results + usage; eval report"
```

---

## Notes for the implementer

- `demos/` and `policy.pt` at the repo root are run artifacts — add them to `.gitignore` if not already ignored (do NOT commit the 100-episode dataset or the checkpoint; only `docs/demo/m2_eval.json` is committed).
- If MPS raises an unsupported-op error during training, set `device = "cpu"` via `pick_device` fallback — the loop is small enough on CPU for this single task.
- Keep `run_episode` untouched beyond Task 2; data-gen and rollout both depend on its stable behavior.
