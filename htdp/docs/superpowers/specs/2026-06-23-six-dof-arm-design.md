# Six-DOF Arm (Real Arm Upgrade) — Design

**Date:** 2026-06-23
**Slice:** v0.2 — real arm upgrade (follow-up to slices 10/14/15; the "menagerie arm" item)
**Status:** approved, ready for implementation plan

## Goal

Replace the vendored 5-DOF placeholder arm (`src/htdp/replay/assets/arm.xml`) with a
hand-authored **6-DOF** arm whose joint axes span SO(3), so `htdp replay-ik
--orientation-cost > 0` can track **full 6-DOF pose** (position *and* orientation), not just
position. The 5-DOF arm had four parallel wrist axes and structurally could not reach an
arbitrary orientation; the 6-DOF arm can.

## Why hand-authored, not literal Menagerie

A real MuJoCo Menagerie model needs either a runtime GitHub fetch (`robot_descriptions`),
which breaks the offline/deterministic property every IK slice has held, or vendored binary
meshes (MBs of STL/OBJ). A hand-authored 6-DOF arm with primitive-geom links — the same
pattern as the existing `arm.xml` — delivers the actual goal (full-pose tracking) while
staying **offline, deterministic, lightweight, mesh-free**. This is a deliberate, documented
choice; the arm is realistic in kinematics (6-DOF, 3-axis wrist), not in appearance.

## Verified live (before this spec)

Using the exact arm below with the existing `ik.py` solve recipe:
- Non-identity target (90° about z, position `[0.5, 0.2, 0.9]`): `pos_err 0.0`,
  `ori_err 0.0` rad → **full pose reached** (the 5-DOF arm could not).
- Synth `right_wrist` position path, `orientation_cost=0.0`, 30 steps: `max_error 0.0`
  (well within the existing `< 0.05` tolerance) → no position-tracking regression.
- `model.nq == 6`; terminal body name `eef` unchanged → `ik.py` needs no code change.

## Architecture

**This is an asset swap.** No change to `src/htdp/replay/ik.py`,
`src/htdp/replay/player.py`, or `src/htdp/cli.py` — joint count is derived everywhere
(`len(qpos)`, `len(joint_trajectory[0])`), the frame/body name `eef` is unchanged, and the
mocap-sphere `replay` path uses its own model. Only the MJCF asset, the joint-count
assertions in tests, and the "5-DOF" wording in docs change.

### The arm (`src/htdp/replay/assets/arm.xml`, full replacement)

```xml
<mujoco model="htdp_arm6">
  <option timestep="0.01"/>
  <worldbody>
    <body name="link0">
      <joint name="j0" type="hinge" axis="0 0 1"/>
      <geom type="capsule" fromto="0 0 0 0 0 0.2" size="0.04"/>
      <body name="link1" pos="0 0 0.2">
        <joint name="j1" type="hinge" axis="0 1 0"/>
        <geom type="capsule" fromto="0 0 0 0 0 0.4" size="0.035"/>
        <body name="link2" pos="0 0 0.4">
          <joint name="j2" type="hinge" axis="0 1 0"/>
          <geom type="capsule" fromto="0 0 0 0 0 0.4" size="0.03"/>
          <body name="link3" pos="0 0 0.4">
            <joint name="j3" type="hinge" axis="0 0 1"/>
            <geom type="capsule" fromto="0 0 0 0 0 0.1" size="0.025"/>
            <body name="link4" pos="0 0 0.1">
              <joint name="j4" type="hinge" axis="0 1 0"/>
              <geom type="capsule" fromto="0 0 0 0 0 0.1" size="0.022"/>
              <body name="eef" pos="0 0 0.1">
                <joint name="j5" type="hinge" axis="1 0 0"/>
                <geom type="sphere" size="0.03"/>
              </body>
            </body>
          </body>
        </body>
      </body>
    </body>
  </worldbody>
</mujoco>
```

Kinematic layout: `j0` base yaw (z), `j1`/`j2` shoulder/elbow pitch (y), then a 3-axis wrist
`j3` (z) / `j4` (y) / `j5` (x) that provides the orientation degrees of freedom. Total reach
≈ 1.2 m (covers the synth workspace, `z ≈ 0.9`). Shipped via the existing hatch artifact glob
`src/htdp/replay/assets/*.xml`.

## Data Flow

Unchanged from slice 15. `replay_release_ik` loads `_ARM_XML` (now 6-DOF), solves, records;
the trajectory CSV simply gains a `q5` column because the joint count is derived.

## Error Handling

No new error paths. `IkUnavailable` (missing extra) unchanged.

## Testing

All gated by the existing module-level `pytest.importorskip("mink")` in
`tests/test_ik_replay.py`.

**Update joint-count assertions (5 → 6):**
- `test_tracks_wrist_within_tolerance`: `all(len(row) == 5 ...)` → `== 6`; keep
  `max_error < 0.05` (verified 0.0).
- `test_cli_replay_ik_out` (slice 14): the q-column assertion
  `[c for c in rows[0] if c.startswith("q")] == ["q0","q1","q2","q3","q4"]` →
  `["q0","q1","q2","q3","q4","q5"]`.

**New demonstrative test — the slice's payoff:**
- `test_arm_reaches_full_pose`: build the model from `htdp.replay.ik._ARM_XML`, run a short
  mink solve (FrameTask `position_cost=1.0, orientation_cost=1.0`) to a **non-identity**
  target (90° about z at `[0.5, 0.2, 0.9]`), assert both `pos_err < 0.01` and
  `ori_err < 0.01` rad. This proves the 6-DOF arm reaches an orientation the 5-DOF arm could
  not. (Self-contained mink usage in the test, mirroring the verified prototype; it imports
  `_ARM_XML` from `ik.py`.)

**Unchanged, must still pass:** `test_deterministic` (two runs equal — values shift with the
new arm but determinism holds), `test_orientation_recorded_at_zero_cost` (target orientations
come from the synth data, not the arm; cost-0 trajectory-equality still holds),
`test_orientation_cost_runs_and_is_deterministic`, all writer tests in `tests/test_ik_export.py`
(hand-built `IkResult`, independent of the arm), and `tests/test_load_pose.py`.

## Determinism

The arm is a fixed committed asset; the mink/daqp solve is deterministic, so trajectories are
reproducible. Existing determinism tests compare two live runs (not golden values), so they
hold despite the changed joint values.

## Files Touched

- Modify: `src/htdp/replay/assets/arm.xml` (full replacement, 5-DOF → 6-DOF)
- Modify: `tests/test_ik_replay.py` (joint-count assertions + new `test_arm_reaches_full_pose`)
- Modify: docs — `docs/ARCHITECTURE.md`, `AGENTS.md`, `docs/ROADMAP.md` (5-DOF → 6-DOF wording)

No code change to `ik.py`/`cli.py`/`player.py`. No new dependency, no new module, no schema
change → no JSON-Schema re-export. `replay/` stays out of the mypy gate.

## Self-Review

- **Placeholders:** none — the full MJCF, exact assertion edits, and concrete tolerances are
  given.
- **Consistency:** the verified-live results back every claim (full pose, position tolerance,
  `nq==6`, `eef` name); the asset-only blast radius is justified by the derived joint count.
- **Scope:** single plan — replace one asset, update joint-count assertions, add one
  demonstrative test, fix "5-DOF" wording in three docs.
- **Ambiguity:** explicitly hand-authored (not literal Menagerie) and why; replace-in-place
  (no selector flag, no second arm); the new test asserts the non-identity full-pose payoff
  with concrete tolerances.
