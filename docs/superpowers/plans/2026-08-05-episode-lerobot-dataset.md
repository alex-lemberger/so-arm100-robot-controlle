# Episode → LeRobot Dataset Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert curated recordings from `data/local/episodes/` into a real LeRobot v3 dataset at `data/local/lerobot_dataset/` that `lerobot-train` can point at, with a human curation checkpoint in between so bad takes get excluded before conversion.

**Architecture:** Two independent Python scripts under `robot_learning/`, run via the project's `.venv-lerobot`. The first generates a contact-sheet image per episode plus an editable curation manifest — a human reviews the images and edits the manifest by hand. The second reads that manifest and uses LeRobot's own `LeRobotDataset.create()`/`add_frame()`/`save_episode()`/`finalize()` writer API to build the dataset, decoding video via PyAV and resampling our 20Hz joint samples to the video's 30fps timeline.

**Tech Stack:** Python 3.12 via `.venv-lerobot` (already has `lerobot`, `av`/PyAV, `pillow`, `numpy`, `pandas`, `pyarrow`, `torch` — confirmed installed, no new dependencies needed), `ffmpeg` CLI (already on PATH, confirmed via `which ffmpeg`).

## Global Constraints

- No test framework in this repo — verification is manual script runs plus the Read tool for visual checks, matching the project-wide convention (see `AGENTS.md`'s Validation section).
- Environment is `.venv-lerobot` (`/Users/alexanderlemberger/so-arm100-robot-controller/.venv-lerobot/bin/python3`), **not** `~/lerobot/.venv` — this work never touches hardware/serial, so the hardware-only venv is irrelevant here.
- Output dataset goes to `data/local/lerobot_dataset/`, already covered by the existing `/data/local/` gitignore rule — do not commit its contents.
- Task label is exactly: `"Pick up a shape piece and insert it into its matching hole on the puzzle board."`
- Camera keys are exactly `observation.images.overview` and `observation.images.wrist` (not `top`).
- `observation.state[t] = action[t-1]` (one-step shift; `state[0] = action[0]`).
- Joint name/order mapping (app key → LeRobot name), in this exact order:
  `base`→`main_shoulder_pan`, `shoulder`→`main_shoulder_lift`, `elbow`→`main_elbow_flex`, `wristPitch`→`main_wrist_flex`, `wristRoll`→`main_wrist_roll`, `gripper`→`main_gripper`. No unit conversion — source values are already plain degrees/percent, matching `svla_so100_pickplace`'s convention.
- Video frame pairing between cameras is by **timestamp**, not index — `overview.webm`'s frame timestamps are authoritative; each `overview` frame is paired with the nearest `wrist` frame by timestamp (camera frame counts differ by up to 2 frames per episode).
- Joint-sample lookup per video frame: nearest sample at-or-before that frame's timestamp, holding the last sample for any frame past the last recorded sample (encoder-flush tail frames).
- Fail loudly (raise, don't skip) on a missing episode directory, missing `metadata.json`, or a `metadata.json` that doesn't parse/match the expected shape.

---

### Task 1: Contact-sheet generator and curation manifest

**Files:**
- Create: `robot_learning/generate_episode_contact_sheets.py`

**Interfaces:**
- Produces: `outputs/episode-review/<episode-name>.jpg` (one 3x2 contact-sheet image per episode found under `data/local/episodes/`) and `outputs/episode-review/curated-episodes.txt` (a manifest listing every discovered episode name, one per line, with a `#`-comment header explaining that lines should be deleted to exclude that episode — this is a template a human edits by hand). Task 2 reads this manifest file's format (plain text, one episode-folder-name per line, `#`-prefixed lines ignored).

- [ ] **Step 1: Write the script**

Create `robot_learning/generate_episode_contact_sheets.py`:

```python
"""Generate a per-episode contact-sheet image (and an editable curation
manifest) from recorded teleoperation episodes, so a human can quickly
flag which ones to include before building a LeRobot dataset from them.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

EPISODES_ROOT = Path("data/local/episodes")
OUTPUT_DIR = Path("outputs/episode-review")
FRAME_PERCENTAGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
GRID_COLS = 3
GRID_ROWS = 2
THUMB_WIDTH = 480


def discover_episodes() -> list[str]:
    if not EPISODES_ROOT.is_dir():
        raise FileNotFoundError(f"No episodes directory at {EPISODES_ROOT}")
    names = sorted(p.name for p in EPISODES_ROOT.iterdir() if p.is_dir())
    if not names:
        raise FileNotFoundError(f"No episode subdirectories found under {EPISODES_ROOT}")
    return names


def extract_frame(video_path: Path, at_seconds: float, out_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{at_seconds:.3f}", "-i", str(video_path),
            "-frames:v", "1", str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def build_contact_sheet(episode_dir: Path, out_path: Path) -> None:
    metadata = json.loads((episode_dir / "metadata.json").read_text())
    duration_s = metadata["durationMs"] / 1000
    overview_file = episode_dir / metadata["observations"]["overview"]["file"]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        thumbs = []
        for i, pct in enumerate(FRAME_PERCENTAGES):
            # Clamp away from the exact end timestamp — ffmpeg -ss at or past
            # the last frame's pts can return no frame at all.
            at_seconds = min(pct * duration_s, duration_s - 0.05)
            frame_path = tmp_dir / f"frame_{i}.jpg"
            extract_frame(overview_file, max(at_seconds, 0.0), frame_path)
            image = Image.open(frame_path)
            aspect = image.height / image.width
            image = image.resize((THUMB_WIDTH, int(THUMB_WIDTH * aspect)))
            thumbs.append(image)

        thumb_w, thumb_h = thumbs[0].size
        sheet = Image.new("RGB", (thumb_w * GRID_COLS, thumb_h * GRID_ROWS))
        for i, thumb in enumerate(thumbs):
            col, row = i % GRID_COLS, i // GRID_COLS
            sheet.paste(thumb, (col * thumb_w, row * thumb_h))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out_path, quality=85)


def write_manifest(episode_names: list[str], out_path: Path) -> None:
    lines = [
        "# Curation manifest: one episode folder name per line.",
        "# Delete a line to exclude that episode from the LeRobot dataset build.",
        "# Lines starting with # are ignored.",
        *episode_names,
    ]
    out_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    episode_names = discover_episodes()
    for name in episode_names:
        episode_dir = EPISODES_ROOT / name
        out_path = OUTPUT_DIR / f"{name}.jpg"
        build_contact_sheet(episode_dir, out_path)
        print(f"Wrote {out_path}")

    manifest_path = OUTPUT_DIR / "curated-episodes.txt"
    write_manifest(episode_names, manifest_path)
    print(f"Wrote manifest listing {len(episode_names)} episodes to {manifest_path}")
    print("Review the contact sheets, then edit the manifest to remove any episodes to exclude.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against the real recorded episodes**

Run: `.venv-lerobot/bin/python3 robot_learning/generate_episode_contact_sheets.py`

Expected: one line of output per episode (`Wrote outputs/episode-review/<name>.jpg`) for every folder under `data/local/episodes/`, then a final line reporting the manifest path and episode count.

- [ ] **Step 3: Visually verify a couple of contact sheets**

Use the Read tool to view two or three of the generated files, e.g. `outputs/episode-review/2026-08-05T17-20-46-310Z.jpg`. Confirm each shows a 3x2 grid of six distinct, real (non-black, non-corrupted) frames of the robot arm and puzzle board — not six copies of the same frame, which would indicate the percentage-based `-ss` seeking isn't actually landing at different points in the video.

- [ ] **Step 4: Verify the manifest**

Run: `cat outputs/episode-review/curated-episodes.txt`

Expected: the three comment lines, followed by all 29 episode folder names (one per line), matching `ls data/local/episodes/`.

- [ ] **Step 5: Commit**

```bash
git add robot_learning/generate_episode_contact_sheets.py
git commit -m "feat: add episode contact-sheet generator for dataset curation review"
```

Note: `outputs/episode-review/` itself is not committed — `outputs/` is already gitignored.

---

## ⚠️ Human Checkpoint — required before Task 2

Task 2 reads `outputs/episode-review/curated-episodes.txt` as the actual list of episodes to convert into the real dataset. **A human must open the contact sheets generated in Task 1, decide which episodes are clean/complete demonstrations, and edit that file by hand** (deleting lines for episodes to exclude) before a real full-dataset build should be run.

Task 2 below does not depend on this having happened yet — its own verification uses a separate, agent-picked smoke-test manifest (see Task 2 Step 4) so the pipeline can be implemented and verified without waiting on human curation. But do not run `build_lerobot_dataset.py` against the real `curated-episodes.txt` for the full 29-episode dataset until a human has actually reviewed and edited it. That full run is explicitly out of scope for this plan.

---

### Task 2: LeRobot dataset builder

**Files:**
- Create: `robot_learning/build_lerobot_dataset.py`

**Interfaces:**
- Consumes: `outputs/episode-review/curated-episodes.txt`-format manifest (plain text, one episode folder name per line, `#`-prefixed lines ignored) from Task 1. Also consumes `data/local/episodes/<name>/{overview.webm,wrist.webm,metadata.json}`, the schema described in Global Constraints.
- Produces: a `LeRobotDataset` on disk at the given `--output` path (default `data/local/lerobot_dataset`), with features `action` (float32, shape `(6,)`), `observation.state` (float32, shape `(6,)`), `observation.images.overview` (video, shape `(720, 1280, 3)`), `observation.images.wrist` (video, shape `(720, 1280, 3)`), fps 30, task string exactly `"Pick up a shape piece and insert it into its matching hole on the puzzle board."`.

- [ ] **Step 1: Write the script**

Create `robot_learning/build_lerobot_dataset.py`:

```python
"""Convert curated recorded episodes (data/local/episodes/) into a LeRobot
v3 dataset, using LeRobot's own writer API so the output format matches
exactly what lerobot-train expects.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import av

from lerobot.datasets.lerobot_dataset import LeRobotDataset

JOINT_NAME_MAP = {
    "base": "main_shoulder_pan",
    "shoulder": "main_shoulder_lift",
    "elbow": "main_elbow_flex",
    "wristPitch": "main_wrist_flex",
    "wristRoll": "main_wrist_roll",
    "gripper": "main_gripper",
}
JOINT_ORDER = ["base", "shoulder", "elbow", "wristPitch", "wristRoll", "gripper"]
LEROBOT_JOINT_NAMES = [JOINT_NAME_MAP[joint] for joint in JOINT_ORDER]

TASK_STRING = "Pick up a shape piece and insert it into its matching hole on the puzzle board."

FEATURES = {
    "action": {"dtype": "float32", "shape": (6,), "names": LEROBOT_JOINT_NAMES},
    "observation.state": {"dtype": "float32", "shape": (6,), "names": LEROBOT_JOINT_NAMES},
    "observation.images.overview": {
        "dtype": "video", "shape": (720, 1280, 3), "names": ["height", "width", "channels"],
    },
    "observation.images.wrist": {
        "dtype": "video", "shape": (720, 1280, 3), "names": ["height", "width", "channels"],
    },
}


def load_manifest(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Manifest not found: {path}")
    lines = path.read_text().splitlines()
    names = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    if not names:
        raise ValueError(f"No episodes listed in manifest {path}")
    return names


def decode_video_frames(path: Path) -> list[tuple[float, np.ndarray]]:
    """Returns [(timestamp_seconds, HWC uint8 RGB array), ...] in playback order."""
    container = av.open(str(path))
    stream = container.streams.video[0]
    frames = []
    for frame in container.decode(stream):
        t_sec = float(frame.pts * stream.time_base)
        frames.append((t_sec, frame.to_ndarray(format="rgb24")))
    container.close()
    return frames


def nearest_frame(frames: list[tuple[float, np.ndarray]], t_sec: float) -> np.ndarray:
    return min(frames, key=lambda item: abs(item[0] - t_sec))[1]


def joints_at(samples: list[dict], t_ms: float) -> dict:
    """Nearest joint sample at-or-before t_ms, holding the last sample for
    any timestamp past the final recorded sample (encoder-flush tail frames)."""
    candidate = samples[0]["joints"]
    for sample in samples:
        if sample["tMs"] <= t_ms:
            candidate = sample["joints"]
        else:
            break
    return candidate


def joints_to_action(joints: dict) -> np.ndarray:
    return np.array([joints[name] for name in JOINT_ORDER], dtype=np.float32)


def validate_episode_dir(episode_dir: Path, name: str) -> None:
    if not episode_dir.is_dir():
        raise FileNotFoundError(f"Episode directory not found: {episode_dir}")
    metadata_path = episode_dir / "metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"metadata.json missing for episode: {name}")
    metadata = json.loads(metadata_path.read_text())
    for key in ("observations", "actions", "durationMs"):
        if key not in metadata:
            raise ValueError(f"metadata.json for {name} is missing required key: {key}")
    for role in ("overview", "wrist"):
        if role not in metadata["observations"]:
            raise ValueError(f"metadata.json for {name} is missing observations.{role}")


def convert_episode(dataset: LeRobotDataset, episode_dir: Path, name: str) -> int:
    validate_episode_dir(episode_dir, name)
    metadata = json.loads((episode_dir / "metadata.json").read_text())
    samples = metadata["actions"]["samples"]
    overview_path = episode_dir / metadata["observations"]["overview"]["file"]
    wrist_path = episode_dir / metadata["observations"]["wrist"]["file"]

    overview_frames = decode_video_frames(overview_path)
    wrist_frames = decode_video_frames(wrist_path)

    prev_action = None
    for t_sec, overview_image in overview_frames:
        t_ms = t_sec * 1000
        joints = joints_at(samples, t_ms)
        action = joints_to_action(joints)
        state = prev_action if prev_action is not None else action
        wrist_image = nearest_frame(wrist_frames, t_sec)

        dataset.add_frame({
            "observation.images.overview": overview_image,
            "observation.images.wrist": wrist_image,
            "action": action,
            "observation.state": state,
            "task": TASK_STRING,
        })
        prev_action = action

    dataset.save_episode()
    return len(overview_frames)


def build_dataset(manifest_path: Path, episodes_root: Path, output_root: Path, repo_id: str) -> None:
    episode_names = load_manifest(manifest_path)
    for name in episode_names:
        validate_episode_dir(episodes_root / name, name)

    dataset = LeRobotDataset.create(
        repo_id=repo_id,
        fps=30,
        features=FEATURES,
        root=output_root,
        robot_type="so100",
    )
    total_frames = 0
    for name in episode_names:
        total_frames += convert_episode(dataset, episodes_root / name, name)
        print(f"Converted episode {name}")

    dataset.finalize()
    print(f"Wrote {len(episode_names)} episodes, {total_frames} frames to {output_root}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="outputs/episode-review/curated-episodes.txt")
    parser.add_argument("--episodes-root", default="data/local/episodes")
    parser.add_argument("--output", default="data/local/lerobot_dataset")
    parser.add_argument("--repo-id", default="local/shape_sort_teleop")
    args = parser.parse_args()
    build_dataset(Path(args.manifest), Path(args.episodes_root), Path(args.output), args.repo_id)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Typecheck-equivalent — import sanity check**

Run: `.venv-lerobot/bin/python3 -c "import robot_learning.build_lerobot_dataset"`

Expected: no output, exit code 0 (confirms no syntax errors and all imports resolve — this repo has no `tsc`-equivalent for Python, so this is the fastest way to catch basic mistakes before a full run).

- [ ] **Step 3: Create a smoke-test manifest (do NOT touch the real curation manifest)**

This step exists so the pipeline can be verified end-to-end without waiting on the human curation checkpoint above. Create a separate file, not `outputs/episode-review/curated-episodes.txt`:

```bash
mkdir -p /tmp/episode-dataset-smoketest
cat > /tmp/episode-dataset-smoketest/manifest.txt <<'EOF'
2026-08-05T17-20-46-310Z
2026-08-05T18-19-21-058Z
2026-08-05T18-25-19-225Z
EOF
```

These three episode names were already visually confirmed to show real, clean footage of the robot manipulating the puzzle board (spot-checked earlier this session). If any of these three folders don't exist under `data/local/episodes/` when you run this (e.g. the local data changed), pick any three other episode folder names present there instead — the specific choice doesn't matter for this smoke test, only that they're real existing episodes.

- [ ] **Step 4: Run the smoke-test conversion**

```bash
.venv-lerobot/bin/python3 robot_learning/build_lerobot_dataset.py \
  --manifest /tmp/episode-dataset-smoketest/manifest.txt \
  --episodes-root data/local/episodes \
  --output /tmp/episode-dataset-smoketest/lerobot_dataset \
  --repo-id local/shape_sort_teleop_smoketest
```

Expected: one `Converted episode <name>` line per episode, then a final `Wrote 3 episodes, <N> frames to /tmp/episode-dataset-smoketest/lerobot_dataset` line. No traceback.

- [ ] **Step 5: Reload and verify shapes/counts**

```bash
.venv-lerobot/bin/python3 -c "
from pathlib import Path
from lerobot.datasets.lerobot_dataset import LeRobotDataset

dataset = LeRobotDataset('local/shape_sort_teleop_smoketest', root=Path('/tmp/episode-dataset-smoketest/lerobot_dataset'))
print('num_episodes:', dataset.num_episodes)
print('num_frames:', dataset.num_frames)
sample = dataset[0]
print('action shape:', sample['action'].shape)
print('observation.state shape:', sample['observation.state'].shape)
print('observation.images.overview shape:', sample['observation.images.overview'].shape)
print('observation.images.wrist shape:', sample['observation.images.wrist'].shape)
assert dataset.num_episodes == 3, f'expected 3 episodes, got {dataset.num_episodes}'
assert sample['action'].shape[-1] == 6, f\"expected action dim 6, got {sample['action'].shape}\"
assert sample['observation.state'].shape[-1] == 6, f\"expected state dim 6, got {sample['observation.state'].shape}\"
print('OK: shapes and episode count check out')
"
```

Expected: prints the values, then `OK: shapes and episode count check out`, no assertion error.

- [ ] **Step 6: Visual round-trip check on one frame**

```bash
.venv-lerobot/bin/python3 -c "
from pathlib import Path
from PIL import Image
from lerobot.datasets.lerobot_dataset import LeRobotDataset

dataset = LeRobotDataset('local/shape_sort_teleop_smoketest', root=Path('/tmp/episode-dataset-smoketest/lerobot_dataset'))
sample = dataset[len(dataset) // 2]
image = sample['observation.images.overview']  # CHW float32 tensor normalized to [0, 1]
array = (image.permute(1, 2, 0).numpy() * 255).astype('uint8')
Image.fromarray(array).save('/tmp/episode-dataset-smoketest/roundtrip_frame.jpg')
print('Wrote /tmp/episode-dataset-smoketest/roundtrip_frame.jpg')
"
```

Then use the Read tool to view `/tmp/episode-dataset-smoketest/roundtrip_frame.jpg`. Confirm it's a real, undistorted frame of the robot arm and puzzle board (matching what the Task 1 contact sheets showed for the same episode) — not a black/green/corrupted frame, which would indicate a colorspace or encoding problem in `convert_episode`'s video handling.

- [ ] **Step 7: DataLoader / collate smoke test (stands in for a full `lerobot-train` dry run)**

```bash
.venv-lerobot/bin/python3 -c "
from pathlib import Path
import torch
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.utils.collate import lerobot_collate_fn

dataset = LeRobotDataset('local/shape_sort_teleop_smoketest', root=Path('/tmp/episode-dataset-smoketest/lerobot_dataset'))
loader = torch.utils.data.DataLoader(dataset, batch_size=4, collate_fn=lerobot_collate_fn)
batch = next(iter(loader))
print('batch action shape:', batch['action'].shape)
print('batch observation.state shape:', batch['observation.state'].shape)
print('batch observation.images.overview shape:', batch['observation.images.overview'].shape)
print('OK: dataset collates into a training-shaped batch without error')
"
```

Expected: prints the batch shapes, then `OK: dataset collates into a training-shaped batch without error`, no exception. This exercises the same collate path `lerobot-train` itself uses (`lerobot.utils.collate.lerobot_collate_fn`), which is a faithful, lower-risk stand-in for a full `lerobot-train` invocation — the full CLI additionally requires a policy config unrelated to whether this dataset itself is well-formed.

- [ ] **Step 8: Clean up smoke-test artifacts**

```bash
rm -rf /tmp/episode-dataset-smoketest
```

Do not delete anything under `data/local/` or `outputs/episode-review/` — those are the real Task 1 outputs, untouched by this smoke test.

- [ ] **Step 9: Commit**

```bash
git add robot_learning/build_lerobot_dataset.py
git commit -m "feat: add LeRobot dataset builder for curated recorded episodes"
```
