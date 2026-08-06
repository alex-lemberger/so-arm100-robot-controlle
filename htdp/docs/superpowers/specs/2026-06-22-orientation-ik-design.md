# Orientation IK — Design

**Date:** 2026-06-22
**Slice:** v0.2 — orientation IK (follow-up to slices 10 + 14)
**Status:** approved, ready for implementation plan

## Goal

Add an opt-in orientation objective to `htdp replay-ik`. Today the IK solve is position-only
(`FrameTask(orientation_cost=0.0)`); the wrist quaternion in the motion stream is loaded
nowhere and never used. Add `--orientation-cost FLOAT` (default `0.0` = unchanged behavior)
that weights wrist-orientation tracking, record the per-step orientation tracking error, and
surface it in the printed summary and the slice-14 trajectory CSV.

## Key constraints (verified live)

- **The vendored arm is 5-DOF** (`arm.xml`: hinges `j0` axis z, `j1`–`j4` axis y — 4 parallel
  axes). It cannot achieve arbitrary 6-DOF pose, so orientation tracking is **best-effort
  least-squares**, not zero-error. This slice wires the orientation *path* end-to-end; full
  pose fidelity awaits the future real (6-DOF) arm slice.
- **Synth orientation is constant identity** (`generate.py`: `qw=1, qx=qy=qz=0` every sample).
  A valid but static target → tests assert orientation error is *bounded and deterministic*,
  not that a non-trivial rotation is achieved.
- **mink API (prototyped live, confirmed):**
  - `from mink.lie.so3 import SO3`; `SO3(wxyz=np.array([w,x,y,z]))` builds a rotation from a
    quaternion.
  - `SE3.from_rotation_and_translation(SO3(wxyz=q), np.array([x,y,z]))` builds a full pose
    target.
  - `mink.FrameTask(..., orientation_cost=c)` accepts the orientation weight.
  - Current eef orientation after a forward pass: `cfg.data.xquat[eid]` (wxyz).
  - Geodesic orientation error (radians):
    `float(np.linalg.norm((SO3(wxyz=target).inverse() @ SO3(wxyz=current)).log()))`
    (`SO3.log()` returns a 3-vector; verified `0.0` for identity-vs-identity).

## Non-Goals

- Changing the default solve. `--orientation-cost 0.0` (default) leaves the slice-10 solve
  byte-identical (same `SE3.from_translation` target), so existing determinism tests hold.
- Replacing or extending the vendored arm (that is the separate "real menagerie arm" slice).
- Making orientation tracking *accurate* — the 5-DOF arm can't. Goal is the wired,
  measured, reproducible path.
- New dependency, new module, or schema change.

## Architecture

### 1. Pose loader — `src/htdp/replay/player.py`

Add `load_release_pose(release_dir) -> dict[str, list[tuple[float, ...]]]` returning 8-tuples
`(timestamp_s, x_m, y_m, z_m, qw, qx, qy, qz)` per tracker (reads the existing motion CSV
columns, which already include `qw,qx,qy,qz`). The existing `load_release_motion` (4-tuples,
consumed by `replay_release` for mocap spheres) is **left unchanged** — orientation is only
needed by the IK path, so a separate loader keeps the position-only consumer untouched.

### 2. IK solve — `src/htdp/replay/ik.py`

`replay_release_ik(release_dir, max_steps=50, ik_iters=10, orientation_cost=0.0) -> IkResult`:

- Use `load_release_pose(...)["right_wrist"]` (8-tuples).
- `FrameTask(..., orientation_cost=orientation_cost)` (was hardcoded `0.0`).
- Per step, target pose:
  - `orientation_cost > 0`: `SE3.from_rotation_and_translation(SO3(wxyz=q), xyz)`.
  - else: `SE3.from_translation(xyz)` (exactly as slice 10 → identical solve at cost 0).
- **Always record** (independent of the solve weight, for the CSV/summary): the target
  quaternion `(qw,qx,qy,qz)` and the per-step orientation error (target quat vs
  `cfg.data.xquat[eid]`). Recording at cost 0 is intentional — it shows how far orientation
  drifts when you don't optimize it.

Enriched `IkResult` (adds three fields to the slice-14 dataclass):

```python
@dataclass
class IkResult:
    joint_trajectory: list[list[float]]
    max_error: float
    timestamps: list[float]
    targets: list[tuple[float, float, float]]
    errors: list[float]
    target_orientations: list[tuple[float, float, float, float]]  # wxyz
    orientation_errors: list[float]                                # radians
    max_orientation_error: float
```

`max_orientation_error = max(orientation_errors)` (or `0.0` when empty).

### 3. CSV writer — `src/htdp/replay/ik.py` (pure, no mink)

`write_ik_trajectory` header gains five trailing columns; the schema is **stable** regardless
of `--orientation-cost` (the data is always present):

```
timestamp_s, q0..q{J-1}, target_x, target_y, target_z, tracking_error_m,
target_qw, target_qx, target_qy, target_qz, orientation_error_rad
```

Each row appends `target_orientations[i]` (4 values) and `orientation_errors[i]`. Empty
trajectory → header-only file with the full (orientation-inclusive) header.

### 4. CLI — `src/htdp/cli.py`

`replay_ik` gains `orientation_cost: float = typer.Option(0.0, "--orientation-cost")`, passed
to `replay_release_ik`. Summary line gains the orientation error:

```
stepped N steps, max tracking error X.XXXX m, max orientation error Y.YYYY rad
```

(`--out`/`--force` from slice 14 unchanged; still write the CSV when `--out` given.)

## Data Flow

`release_dir` → `load_release_pose` → `right_wrist` 8-tuples → per-step IK solve (position,
plus orientation when weighted) → enriched `IkResult` → summary line + (`--out`) CSV.

## Error Handling

- Missing `replay` extra → `IkUnavailable` (unchanged).
- `--out` overwrite without `--force` → `FileExistsError` → exit 1 (unchanged).
- Negative `--orientation-cost` is not specially handled — mink treats the weight as given;
  out of scope to validate (consistent with `max_steps`/`ik_iters` being unvalidated).

## Testing

**Writer tests — `tests/test_ik_export.py` (NOT gated, must RUN).** Update the slice-14
`_sample()` to include `target_orientations=[(1.0,0.0,0.0,0.0),(1.0,0.0,0.0,0.0)]`,
`orientation_errors=[0.0, 0.0]`, `max_orientation_error=0.0`, and update expected header +
row 0 to the new 12-column schema. Update the empty-result test's expected header to the
orientation-inclusive header.

**Gated IK tests — `tests/test_ik_replay.py` (module `importorskip("mink")`):**
- `test_orientation_recorded_at_zero_cost`: default solve records `target_orientations`
  (length == steps, each ≈ `(1,0,0,0)`) and `orientation_errors` (length == steps); the
  joint trajectory is **identical** to a slice-10 position-only run (assert
  `replay_release_ik(rel, max_steps=10).joint_trajectory ==
  replay_release_ik(rel, max_steps=10, orientation_cost=0.0).joint_trajectory`) — proving the
  default path is unchanged.
- `test_orientation_cost_runs_and_is_deterministic`: `orientation_cost=1.0` produces a result
  with `max_orientation_error` a finite float `>= 0.0`, and two identical runs give equal
  `joint_trajectory` (determinism). Do not assert a tight orientation error (5-DOF arm).
- `test_cli_orientation_cost_out`: `replay-ik <rel> --orientation-cost 1.0 --out <csv>` exit
  0; summary contains `max orientation error`; CSV header ends with
  `target_qw,target_qx,target_qy,target_qz,orientation_error_rad`.

Existing slice-10/14 tests (`test_deterministic`, `test_tracks_wrist_within_tolerance`,
`test_cli_replay_ik`, `test_cli_replay_ik_out*`) must still pass unchanged (default cost 0).

## Determinism

`--orientation-cost 0.0` (default) → identical solve to slice 10 → identical CSV. Any fixed
cost → deterministic mink/daqp solve → reproducible trajectory and errors.

## Files Touched

- Modify: `src/htdp/replay/player.py` (add `load_release_pose`)
- Modify: `src/htdp/replay/ik.py` (`IkResult` fields, `replay_release_ik` orientation path +
  recording, `write_ik_trajectory` columns)
- Modify: `src/htdp/cli.py` (`--orientation-cost`, summary line)
- Modify: `tests/test_ik_export.py` (orientation columns in `_sample`/expected)
- Modify: `tests/test_ik_replay.py` (orientation tests, gated)
- Modify: docs — `docs/ARCHITECTURE.md`, `AGENTS.md`, `docs/ROADMAP.md`

No new dependency, no new module, no schema change → no JSON-Schema re-export. `replay/` and
`cli.py` stay out of the mypy gate (unchanged policy).

## Self-Review

- **Placeholders:** none — dataclass fields, the verified mink calls, the exact CSV header,
  and concrete test assertions are all spelled out.
- **Consistency:** orientation recorded regardless of cost (stable CSV schema); default cost 0
  keeps slice-10/14 behavior, asserted by `test_orientation_recorded_at_zero_cost`'s
  trajectory-equality check; new loader leaves `load_release_motion` untouched; writer stays
  pure (no mink) so its tests still run unguarded.
- **Scope:** single plan — one loader, one solve param + recording, three CSV columns groups,
  one CLI option, test updates, docs.
- **Ambiguity:** "orientation IK" is opt-in (flag, default 0) not always-on; best-effort on
  the 5-DOF arm (no tight error assertion); orientation columns always present; orientation
  error is the geodesic angle in radians via the verified `SO3` log expression.
