# Release-Level rosbag2 Export — Design

**Date:** 2026-06-22
**Slice:** v0.2 — ROS 2 / rosbag2 export (motion + events)
**Status:** approved, ready for implementation plan

## Goal

Add `htdp export-release-rosbag <release_dir> <out_dir> [--force]`: export a packaged
release into one rosbag2 (mcap) bag **per session**. The output inherits the release's
consent filtering (modalities dropped during packaging are simply absent from the
source, so they cannot appear in the bags). This slice exports **motion + events**
only; EEG is deferred to a follow-up slice (mirrors the slice-4 → slice-6 rhythm where
Motion-BIDS shipped before EEG-BIDS).

This is the ROS 2 sibling of `export-release-bids` (slice 7): same source (a packaged
release), same consent-inheritance property, same read-only export discipline.

## Non-Goals

- EEG export (no idiomatic ROS message; deserves its own design).
- `tf` / `TransformStamped` (PoseStamped only).
- Single-raw-session command (release source only this slice).
- sqlite3 (`.db3`) storage format (mcap only).
- One-bag-for-the-whole-release (one bag **per session**).

## Architecture

New module `src/htdp/export/rosbag.py`, parallel to `bids.py`. No shared code beyond
`sanitize` from `export/labels.py`. The release-loop / force-guard / `data/` discovery
structure mirrors `export_release_bids` but writes bags instead of BIDS trees.

```
src/htdp/export/rosbag.py
  RosbagExportError(RuntimeError)
  _write_session_bag(bag_dir: Path, raw_dir: Path) -> None
  export_release_rosbag(release_dir: Path, out_dir: Path, force: bool = False) -> Path
```

### `_write_session_bag(bag_dir, raw_dir) -> None`

Writes a single rosbag2 (mcap) bag into `bag_dir` (the caller has already chosen the
per-session directory name; this function owns the bag's internal contents).

1. Read `raw_dir/session.json` and `raw_dir/device_config.json`. Missing either →
   `RosbagExportError`.
2. Select `role == "motion"` streams. None → `RosbagExportError` (a session with no
   motion cannot be exported, same rule as Motion-BIDS).
3. For each motion stream (one tracker per CSV file):
   - Topic `/motion/<sanitize(tracker_name)>`, type `geometry_msgs/msg/PoseStamped`.
   - One message per CSV row.
4. Select the `role == "events"` stream if present (releases always carry it for synth
   sessions; treat as optional). Topic `/events`, type `std_msgs/msg/String`, one
   message per row.

### `export_release_rosbag(release_dir, out_dir, force) -> Path`

1. `data_dir = release_dir / "data"`. Not a directory → `RosbagExportError`.
2. `session_dirs = sorted(p for p in data_dir.iterdir() if p.is_dir())`. Empty →
   `RosbagExportError`.
3. Force-guard the **whole** `out_dir`: if it exists and not `force` → error; if `force`
   → `shutil.rmtree`. Then `out_dir.mkdir(parents=True)`. (No partial writes: validate
   source before creating `out_dir`.)
4. For each session dir `sd`: read `session.json`, per-session bag dir =
   `out_dir / sanitize(session.session_id)`. `session_id` is unique within a release, so
   no collision-handling (no `ses-` analogue) is needed.
5. Call `_write_session_bag(bag_dir, sd)`.
6. Return `out_dir`.

## Message Mapping

Raw motion CSV columns (per-tracker file):
`timestamp_s, tracker_id, x_m, y_m, z_m, qw, qx, qy, qz, quality, defect_tag`

**PoseStamped** (`geometry_msgs/msg/PoseStamped`):
- `header.stamp` ← `timestamp_s` split into `(sec, nanosec)`.
- `header.frame_id` ← tracker name.
- `pose.position.{x,y,z}` ← `x_m, y_m, z_m`.
- `pose.orientation.{x,y,z,w}` ← `qx, qy, qz, qw`.
- `quality` and `defect_tag` are **dropped** (Motion-BIDS likewise drops `defect_tag`).

Raw events CSV columns:
`timestamp_s, event_id, label, phase, source, confidence, notes`

**String** (`std_msgs/msg/String`):
- `data` ← `label`.
- `std_msgs/String` has no header; onset is carried solely by the rosbag2 per-message
  log time.

**Time source:** every message's rosbag2 log time = `int(round(timestamp_s * 1e9))` ns.
PoseStamped additionally carries the same value in `header.stamp`. Bag start/end times
are whatever the messages imply (no artificial t0 rebase). `timestamp_s` is already the
session-relative time base produced upstream.

## Library & Optional Dependency

Use **`rosbags`** (pure-python; writes rosbag2 mcap without a ROS installation). Real
`rclpy` / `rosbag2` would require a full ROS install and breaks the established
optional-dependency pattern.

Add a new extra to `pyproject.toml`:

```toml
[project.optional-dependencies]
replay = ["mujoco>=3.1"]
ingest = ["pyxdf>=1.16"]
rosbag = ["rosbags>=0.10"]
dev = [...]
```

This mirrors `replay`/`ingest`: the module imports `rosbags` lazily (inside the
functions, or guarded) so the package still imports without the extra; the CLI command
surfaces a clear error if the extra is absent.

mypy: `rosbags` may be untyped. If `mypy src/htdp/export` complains, add a narrow
`type: ignore[...]` at the import or a `[[tool.mypy.overrides]]` `ignore_missing_imports`
entry for `rosbags.*` — decided in the plan against actual mypy output, not guessed.

## Determinism

The "same release → identical output" property holds at the **logical** level, not the
byte level: mcap embeds a library-version/profile string, so two runs are not guaranteed
byte-identical. Therefore the determinism / correctness test **reads the bag back**
(reopen with `rosbags`, assert the topic set, per-topic message counts, and the first
PoseStamped's position/orientation values) rather than hashing bytes. This avoids a
fragile, false-failing byte-comparison.

## Errors

All raise `RosbagExportError`:
- `release_dir/data/` missing or not a directory.
- Release has no session directories.
- `out_dir` exists and `force` is False.
- Session missing `session.json` or `device_config.json`.
- Session has no motion stream.

## CLI

`src/htdp/cli.py`, new command after the BIDS export commands:

```
htdp export-release-rosbag <release_dir> <out_dir> [--force]
```

Lazy-imports `export_release_rosbag` / `RosbagExportError`; on `RosbagExportError`
prints `error: <msg>` to stderr and exits 1; on success prints `wrote <out_dir>`.
Same shape as the `export-release-bids` command.

## Testing

New `tests/test_release_rosbag_export.py`, all gated `pytest.importorskip("rosbags")`:

- **Happy path:** two-subject release → `out/<session_id>/` bags exist; read each back,
  assert topics `/motion/<tracker>` (one per tracker) + `/events`, message counts equal
  the source CSV row counts, first PoseStamped values match the raw CSV first row.
- **Events topic:** `/events` present with String messages; `data` == source labels.
- **Missing `data/`** → `RosbagExportError`.
- **Empty release** → `RosbagExportError`.
- **Force overwrite:** second export without `force` raises; with `force` succeeds.
- **No-motion session** → `RosbagExportError` (construct a session dir with motion
  streams stripped, or assert via a unit call to `_write_session_bag`).
- **Consent inheritance** (optional, alongside the eeg-absent BIDS test): a release that
  dropped a modality still exports motion+events fine and the dropped modality is simply
  not present — implicit, since EEG is not exported this slice anyway; a lightweight
  assertion that export succeeds on a consent-filtered release suffices.

CLI test appended to `tests/test_cli_shell.py` (gated on `rosbags`): happy path exit 0 +
bag dir exists; bad release dir exit 1 + `error:` in output.

**Critical (false-green guard):** `rosbags` is NOT currently installed. The executor
MUST `uv sync --extra rosbag --extra dev` and confirm the gated tests **RUN, not SKIP**
before claiming green. (Prior slice shipped 3 defects behind skipped optional-dep tests
— see the local-model-review lesson.)

## Files Touched

- New: `src/htdp/export/rosbag.py`
- New: `tests/test_release_rosbag_export.py`
- Modify: `src/htdp/cli.py` (add command)
- Modify: `tests/test_cli_shell.py` (append CLI test)
- Modify: `pyproject.toml` (add `rosbag` extra; possibly mypy override)
- Modify: docs — `docs/DATA_CONTRACT.md`, `AGENTS.md`, `docs/ROADMAP.md`

No other `export/*`, `ingest`, `release`, `synth`, `schemas` files change. No persisted
schema change → no JSON-Schema re-export.

## Self-Review

- **Placeholders:** none — every interface, column mapping, topic, and error is concrete.
- **Consistency:** per-session bag named `sanitize(session_id)` (unique) matches the
  "no collision logic" claim; message mapping matches the verified raw CSV headers;
  optional-dep extra mirrors existing `replay`/`ingest` entries.
- **Scope:** single implementation plan — one module, one CLI command, one test file +
  appends. Motion+events only; EEG/tf/sqlite3/single-session explicitly out.
- **Ambiguity:** time base fixed to `int(round(timestamp_s * 1e9))` ns; determinism
  resolved as read-back (not byte hash); String carries onset via log time only.
