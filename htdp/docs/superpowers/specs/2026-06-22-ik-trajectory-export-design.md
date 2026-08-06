# IK Trajectory Export — Design

**Date:** 2026-06-22
**Slice:** v0.2 — IK trajectory export (follow-up to slice 10)
**Status:** approved, ready for implementation plan

## Goal

Persist the joint trajectory that `htdp replay-ik` (slice 10) already computes. Today the
command solves differential IK over a release's `right_wrist` Cartesian path, then discards
everything but a printed `max_error` summary. Add an optional `--out PATH` that writes the
per-step joint trajectory (plus source target and tracking error) to a CSV hand-off file.

## Non-Goals

- A second CLI command — extend the existing `replay-ik` rather than add `export-ik`.
- Parquet / rosbag / BIDS output — CSV only (a trajectory is a hand-off artifact, not a
  pipeline stage). Other formats can wrap the CSV later if ever needed.
- Changing the IK math, the vendored arm, orientation handling, or `max_steps`/`ik_iters`
  semantics. Position-only IK from slice 10 is unchanged.
- Re-running IK in a separate step — the trajectory is written from the single existing solve.
- Any change to the raw / release / processed schemas.

## Background (verified, slice 10)

`src/htdp/replay/ik.py` has `IkUnavailable`, `IkResult{joint_trajectory: list[list[float]],
max_error: float}`, and `replay_release_ik(release_dir, max_steps=50, ik_iters=10) -> IkResult`.
The solve loop already has, per step `i`: the source wrist sample `wrist[i] = [t, x, y, z]`
(so a timestamp and the Cartesian target), the post-solve `cfg.data.qpos` (the joint row,
length 5 for the 5-hinge arm), and `err = ||xpos[eef] - target||`. Only `joint_trajectory`
and `max_error` survive into `IkResult`; the timestamp, target, and per-step error are
dropped. `mink`/`mujoco`/`daqp` come from the optional `replay` extra; `replay/` is
intentionally NOT in the mypy gate. CLI command `replay_ik` lives in `src/htdp/cli.py`.

## Architecture

Two units, split so the file writer needs no optional dependency:

### 1. Enrich `IkResult` (in `src/htdp/replay/ik.py`)

```python
@dataclass
class IkResult:
    joint_trajectory: list[list[float]]
    max_error: float
    timestamps: list[float]
    targets: list[tuple[float, float, float]]
    errors: list[float]
```

`replay_release_ik` populates the three new lists inside the existing per-step loop
(append `wrist[i][0]`, `(x, y, z)`, and the computed `err`). All four per-step lists
(`joint_trajectory`, `timestamps`, `targets`, `errors`) have equal length `n`. `max_error`
is unchanged (`max(errors)`, or `0.0` when `n == 0`).

### 2. Pure CSV writer (in `src/htdp/replay/ik.py`, no mujoco/mink import)

```python
def write_ik_trajectory(result: IkResult, out_path: Path, *, force: bool = False) -> Path
```

- Uses only the stdlib `csv` module — **no** `mink`/`mujoco`/`numpy` import, so it is unit-
  testable from a hand-built `IkResult` **without** the `replay` extra (these tests RUN, not
  skip — sidestepping this project's recurring false-green-on-skip risk).
- Header (joint count `J = len(result.joint_trajectory[0])`, `0` if empty):
  `timestamp_s, q0, ..., q{J-1}, target_x, target_y, target_z, tracking_error_m`.
- One row per step `i`: `timestamps[i]`, the `J` joint values, `targets[i]` unpacked, `errors[i]`.
- Floats written with Python's default `str()`/`csv` repr (deterministic for fixed inputs).
- `out_path` exists and not `force` → raise `FileExistsError` (caught at CLI → exit 1).
- `out_path.parent` missing → raise (do not silently `mkdir`); explicit failure.

### 3. CLI (`src/htdp/cli.py`, extend `replay_ik`)

```
htdp replay-ik <release_dir> [--max-steps N] [--out PATH] [--force]
```

- New options: `out: Path | None = typer.Option(None, "--out")`, `force: bool =
  typer.Option(False, "--force")`.
- Behavior unchanged when `--out` omitted: run IK, print the existing summary.
- When `--out` given: run IK (same call), then `write_ik_trajectory(result, out, force=force)`,
  print the summary plus a `wrote <path> (<n> steps)` line.
- `IkUnavailable` → `error: <msg>` stderr, exit 1 (existing). `FileExistsError` (no `--force`)
  → `error: <msg>` stderr, exit 1.

## Data Flow

`release_dir` → `load_release_motion` → `right_wrist` path → per-step IK solve →
enriched `IkResult` (in memory) → (`--out`) → `write_ik_trajectory` → CSV file.

## Error Handling

- Missing `replay` extra → `IkUnavailable` (unchanged).
- `--out` over an existing file without `--force` → `FileExistsError` → exit 1.
- `--out` parent directory missing → underlying `OSError` → surfaced as exit 1.
- Empty trajectory (`max_steps`/path yields 0 steps) → writes a header-only CSV (joint
  count 0 → `timestamp_s, target_x, target_y, target_z, tracking_error_m`), exit 0.

## Testing

`tests/` — split by dependency so writer tests never skip.

**Writer tests (NO `replay` extra — always RUN), new `tests/test_ik_export.py`:**
- Hand-build `IkResult(joint_trajectory=[[0.1, 0.2], [0.3, 0.4]], max_error=0.5,
  timestamps=[0.0, 0.1], targets=[(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)], errors=[0.1, 0.5])`,
  call `write_ik_trajectory(result, tmp_path/"t.csv")`, read back with `csv.reader`:
  - header == `["timestamp_s","q0","q1","target_x","target_y","target_z","tracking_error_m"]`
  - 2 data rows; row 0 == `["0.0","0.1","0.2","1.0","2.0","3.0","0.1"]` (string compare).
- Overwrite guard: writing to an existing path without `force` raises `FileExistsError`;
  with `force=True` it overwrites (assert new content replaces old).
- Empty result (`IkResult([], 0.0, [], [], [])`) → header-only file with the 0-joint header.

**End-to-end test (REQUIRES `replay` extra — gated, may skip), append to the existing IK
test module:** run `replay_release_ik` on a synth release (reuse the slice-10 fixture),
then `write_ik_trajectory` to a tmp path; assert the CSV row count == `len(result.timestamps)`
and the header q-column count == 5 (the arm's joint count). No per-test skip marker needed —
`tests/test_ik_replay.py` already has a module-level `pytest.importorskip("mink")` (line 10)
that gates every test in the file, so appended tests inherit the gate.

**CLI test:** `replay-ik <release> --out <path>` exit 0, file exists, `wrote` in output —
gated with the same importorskip as the e2e test (CLI path needs real IK).

## Determinism

Same release + same `max_steps`/`ik_iters` → same `IkResult` (slice 10 is deterministic) →
byte-identical CSV (stdlib `csv`, fixed float repr, fixed row order).

## Files Touched

- Modify: `src/htdp/replay/ik.py` (enrich `IkResult`, populate new lists, add `write_ik_trajectory`)
- Modify: `src/htdp/cli.py` (`--out` / `--force` on `replay_ik`)
- Create: `tests/test_ik_export.py` (writer unit tests, no extra)
- Modify: `tests/test_ik_replay.py` (e2e + CLI export tests, gated)
- Modify: docs — `docs/ARCHITECTURE.md`, `AGENTS.md`, `docs/ROADMAP.md`

No new dependency (stdlib `csv`), no new module file beyond the test, no schema change →
no JSON-Schema re-export. `replay/` stays out of the mypy gate (unchanged policy).

## Self-Review

- **Placeholders:** none — dataclass fields, writer signature, header layout, exact test
  rows, and CLI options are all concrete.
- **Consistency:** `IkResult` field names used identically in writer, tests, and the solve
  loop; joint count derived from `len(joint_trajectory[0])` everywhere (no hardcoded 5 in the
  writer); `--force` mirrors the `export-release-*` convention.
- **Scope:** single plan — enrich one dataclass, add one pure writer, two CLI options, two
  test groups, docs.
- **Ambiguity:** CSV-only stated; `--out` omitted = unchanged behavior; empty trajectory =
  header-only file (not error); writer takes no optional dep so its tests cannot false-green
  by skipping; e2e/CLI tests gated exactly like slice-10's.
