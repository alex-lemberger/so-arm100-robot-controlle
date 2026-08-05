# Episode → LeRobot Dataset Conversion Design

## Context

The Wireless Tele-Op & Vision panel's episode recorder (`src/components/GamepadVisionOverlay.tsx`, saved via `POST /api/episodes`) has produced 29 demonstration episodes at `data/local/episodes/<timestamp>/{overview.webm,wrist.webm,metadata.json}` — real recordings of the SO-ARM100 manipulating a wooden shape-sorting puzzle (circle/triangle/square/diamond pieces into matching holes), the actual target task described in `AGENTS.md`'s "Vision and learning direction" section.

These are quality-checked at the file level: all 29 decode cleanly, video durations and frame counts match their `metadata.json`, and both cameras are framed correctly. This is the app's own recording format, unrelated to LeRobot's dataset format — `lerobot-train` cannot consume it directly. This spec covers converting curated episodes into a proper LeRobot v3 dataset.

**Explicitly out of scope:** actually training a policy on the resulting dataset. This spec produces a dataset only; training is a separate follow-up once the dataset exists and has been reviewed.

## Source Data Format

Each `metadata.json`:
```json
{
  "schemaVersion": 1,
  "startedAt": "<ISO timestamp>",
  "durationMs": <number>,
  "observations": {
    "overview": { "file": "overview.webm", "settings": { ...MediaTrackSettings incl. width/height/frameRate... } },
    "wrist": { "file": "wrist.webm", "settings": { ... } }
  },
  "actions": {
    "type": "commanded_joint_target",
    "unit": { "base": "degrees", "shoulder": "degrees", "elbow": "degrees", "wristPitch": "degrees", "wristRoll": "degrees", "gripper": "percent" },
    "sampleRateHz": 20,
    "samples": [ { "tMs": <number>, "joints": { "base": <number>, "shoulder": <number>, "elbow": <number>, "wristPitch": <number>, "wristRoll": <number>, "gripper": <number> } }, ... ]
  },
  "note": "Joint samples are commanded UI targets, not measured follower-arm position telemetry."
}
```

Videos are VP9-in-WebM, ~1280x720, ~30fps (from `settings.frameRate`), streamed (unknown container duration — must be read via full decode, not container metadata).

## Reference: Existing LeRobot Dataset

`data/external/svla_so100_pickplace/` (LeRobot v3.0 format) was inspected to ground this design:
- Layout: `data/chunk-000/file-000.parquet` (per-frame `action`, `observation.state`, `timestamp`, `frame_index`, `episode_index`, `index`, `task_index`), `meta/info.json`, `meta/stats.json`, `meta/tasks.parquet`, `meta/episodes/chunk-000/file-000.parquet`, `videos/observation.images.<key>/chunk-000/file-000.mp4`.
- `action`/`observation.state`: float32, shape `[6]`, names `main_shoulder_pan`/`main_shoulder_lift`/`main_elbow_flex`/`main_wrist_flex`/`main_wrist_roll`/`main_gripper`, fps 30 (one sample per video frame).
- Values inspected directly from the parquet file are **plain degrees** (e.g. shoulder_lift ranging ~-87°) and a percent-like gripper value (~0-27 in the sampled slice) — i.e. the same units our `metadata.json` already uses. No unit/scale conversion needed, only joint renaming/reordering.
- LeRobot ships an official writer API for producing this format: `LeRobotDataset.create(...)` then per-frame `add_frame(dict)` and per-episode `save_episode()` (`~/lerobot/src/lerobot/datasets/lerobot_dataset.py`). This handles parquet schema, video chunking/encoding, and stats computation internally — this design uses that API rather than hand-writing the format.

## Decisions

- **Curation gate:** episodes are reviewed before conversion (see below) — not all 29 are assumed usable.
- **Task label:** one single task string for the whole dataset — `"Pick up a shape piece and insert it into its matching hole on the puzzle board."` — matching how `svla_so100_pickplace` labels its single task. Shape variation across episodes is within-task diversity, not separate tasks.
- **`observation.state` derivation:** `state[t] = action[t-1]` (one-step shift; `state[0] = action[0]` since there is no prior step). This is more honest than duplicating `action` into `state`, given the recordings only capture commanded targets, not measured follower position (`metadata.json`'s own `note` field flags this).
- **Camera keys:** `observation.images.overview` / `observation.images.wrist`, matching this app's own naming everywhere else (not `top`, which is `svla_so100_pickplace`'s key — the two datasets are different tasks/hardware angles, so exact key alignment isn't load-bearing for future co-training).
- **fps:** target dataset fps is 30 (matches video), not the source's 20Hz action sampling.
- **Trailing-frame edge case:** for any video frame whose timestamp exceeds the last recorded joint sample's `tMs` (durations differ by up to ~0.3s in a few episodes — encoder-flush tail frames, not missing data), hold the last sample's joint values rather than erroring.
- **Environment:** `.venv-lerobot` (the project's own venv, already used for `lerobot-record`/training per `AGENTS.md`), not `~/lerobot/.venv` (only needed for hardware/serial access, irrelevant here).
- **Output location:** `data/local/lerobot_dataset/`, gitignored (already covered by the existing `/data/local/` rule), not pushed to the HF Hub — treated as a local artifact, same as `data/external/`.

## Components

### 1. Curation contact sheets (`robot_learning/generate_episode_contact_sheets.py`)

For each of the 29 episodes, extract 6 frames from `overview.webm` at 0%, 20%, 40%, 60%, 80%, and 100% of the episode's `durationMs` (via ffmpeg `-ss`) and tile them 3x2 into a single grid image (via ffmpeg's `tile` filter), written to a scratch output directory (e.g. `outputs/episode-review/<timestamp>.jpg` — `outputs/` is already gitignored). One image per episode, so you can flip through all 29 quickly and identify which to exclude, rather than watching full playback for each. Ambiguous ones you open directly in a video player.

Output: a plain-text curation manifest, e.g. `outputs/episode-review/curated-episodes.txt`, one episode timestamp-folder-name per line — you edit this by hand after reviewing the contact sheets to list only the episodes to include. The conversion script (below) reads this file rather than blindly converting every folder under `data/local/episodes/`.

### 2. Dataset conversion (`robot_learning/build_lerobot_dataset.py`)

Reads the curation manifest, then for each listed episode:
1. Loads `metadata.json`.
2. Decodes `overview.webm` frame-by-frame (ffmpeg/PyAV) — this camera's frame timestamps are authoritative for the dataset's per-frame timeline. Decodes `wrist.webm` frame-by-frame too, and for each `overview` frame timestamp, picks the nearest `wrist` frame **by timestamp**, not by index — the two cameras' frame counts differ by up to 2 frames on some episodes (observed during quality-checking), so index-based pairing would drift.
3. For each `overview` frame's timestamp, finds the nearest joint sample at or before that timestamp (holding the last sample for any trailing frames past the last recorded sample, per the edge case above) to build that frame's `action` vector, mapped/renamed to LeRobot's so100 joint names/order.
4. Computes `observation.state[t] = action[t-1]` (shifted).
5. Calls `dataset.add_frame({...})` per frame with both camera images, `action`, `observation.state`, and the single task string.
6. Calls `dataset.save_episode()` once all of that episode's frames are added.

Run once for the whole curated set, producing `data/local/lerobot_dataset/`.

### 3. Verification (part of the same script, or a small follow-up check)

- Reload the written dataset with `LeRobotDataset(root="data/local/lerobot_dataset")` (read mode) and assert episode count matches the curation manifest, frame count matches the sum of per-episode video frames, and feature shapes match `[6]` for `action`/`observation.state`.
- Decode one frame back out of the written video and visually compare it (via the Read tool, as an image) against the corresponding source webm frame at the same timestamp, to confirm the video round-tripped correctly through re-encoding.
- Run `lerobot-train`'s dataset/config validation against the new dataset (not a real training run — just confirm it loads without a schema error), to catch any format mismatch before attempting real training later.

## Error Handling

- Missing/corrupt episode folder listed in the curation manifest: fail loudly with the episode name, don't silently skip.
- A `metadata.json` that fails schema validation (wrong types, missing fields): fail loudly, same as above — don't guess.
- No transactional rollback beyond what `LeRobotDataset`'s own writer provides — this is a one-shot local script, re-run from scratch (delete `data/local/lerobot_dataset/` and re-run) if something goes wrong partway, rather than trying to resume.

## Testing

No test framework in this repo (matches the project-wide convention). Verification is the reload/spot-check/dataset-validation steps in Components §3, run manually after the conversion script completes, plus visual review of the curation contact sheets before conversion runs at all.
