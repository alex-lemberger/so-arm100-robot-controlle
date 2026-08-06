# Six-DOF Arm Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the vendored 5-DOF placeholder arm with a hand-authored 6-DOF arm so `replay-ik --orientation-cost > 0` can track full 6-DOF pose.

**Architecture:** Pure asset swap — replace `src/htdp/replay/assets/arm.xml` with a 6-DOF MJCF (axes spanning SO(3), terminal body still `eef`). No code change to `ik.py`/`cli.py`/`player.py` (joint count is derived everywhere). Update the joint-count assertions in `tests/test_ik_replay.py` (5→6), add one demonstrative full-pose test, and fix "5-DOF" wording in docs.

**Tech Stack:** MuJoCo MJCF (XML), mink/mujoco/daqp via the optional `replay` extra, pytest.

## Global Constraints

- Hand-authored 6-DOF arm with primitive geoms — NO network fetch, NO vendored meshes (stay offline/deterministic/lightweight).
- Terminal body name stays `eef`; the MJCF keeps `<option timestep="0.01"/>`. Joint count becomes 6 (`model.nq == 6`).
- No code change to `src/htdp/replay/ik.py`, `src/htdp/replay/player.py`, or `src/htdp/cli.py`.
- No new dependency, no new module, no schema change → no JSON-Schema re-export. `replay/` stays out of the mypy gate.
- The arm ships via the existing hatch artifact glob `src/htdp/replay/assets/*.xml` (already in `pyproject.toml`) — no packaging change.
- `tests/test_ik_replay.py` has a module-level `pytest.importorskip("mink")` (line 10); all tests there are gated and must RUN (not skip) when the `replay` extra is synced.
- Verified live: this exact arm gives position `max_error 0.0` over 30 synth steps (< 0.05) and reaches a non-identity pose (90° about z at `[0.5,0.2,0.9]`) with `pos_err 0.0`, `ori_err 0.0`.

---

### Task 1: Swap to the 6-DOF arm

**Files:**
- Modify: `src/htdp/replay/assets/arm.xml` (full replacement, 5-DOF → 6-DOF)
- Modify: `tests/test_ik_replay.py` (joint-count assertions 5→6 + new `test_arm_reaches_full_pose`)

**Interfaces:**
- Consumes: existing `replay_release_ik`, `_ARM_XML` (a `Path`, importable without mink) from `src/htdp/replay/ik.py`; the verified mink `FrameTask`/`SO3`/`SE3` API.
- Produces: a 6-DOF arm (`model.nq == 6`); `replay_release_ik` now returns 6-element joint rows and the CSV gains a `q5` column (both derived, no code change).

- [ ] **Step 1: Update the joint-count assertions to expect 6**

In `tests/test_ik_replay.py`, line 29, change:

```python
    assert all(len(row) == 5 for row in res.joint_trajectory)
```

to:

```python
    assert all(len(row) == 6 for row in res.joint_trajectory)
```

In `tests/test_ik_replay.py`, line ~80 (inside `test_cli_replay_ik_out`), change:

```python
    assert [c for c in rows[0] if c.startswith("q")] == ["q0", "q1", "q2", "q3", "q4"]
```

to:

```python
    assert [c for c in rows[0] if c.startswith("q")] == ["q0", "q1", "q2", "q3", "q4", "q5"]
```

- [ ] **Step 2: Add the full-pose demonstrative test**

Append to `tests/test_ik_replay.py`:

```python
def test_arm_reaches_full_pose(tmp_path: Path):
    import math

    import mink
    import mujoco
    import numpy as np
    from mink.lie.se3 import SE3
    from mink.lie.so3 import SO3

    from htdp.replay.ik import _ARM_XML

    model = mujoco.MjModel.from_xml_path(str(_ARM_XML))
    data = mujoco.MjData(model)
    cfg = mink.Configuration(model)
    cfg.update(data.qpos)
    task = mink.FrameTask(
        frame_name="eef",
        frame_type="body",
        position_cost=1.0,
        orientation_cost=1.0,
        lm_damping=1.0,
    )
    limits = [mink.ConfigurationLimit(model)]
    eid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "eef")
    pos = np.array([0.5, 0.2, 0.9])
    quat = np.array([math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4)])  # 90deg about z
    for _ in range(200):
        task.set_target(SE3.from_rotation_and_translation(SO3(wxyz=quat), pos))
        vel = mink.solve_ik(cfg, [task], model.opt.timestep, "daqp", limits=limits)
        cfg.integrate_inplace(vel, model.opt.timestep)
    mujoco.mj_forward(model, cfg.data)
    pos_err = float(np.linalg.norm(cfg.data.xpos[eid] - pos))
    ori_err = float(
        np.linalg.norm((SO3(wxyz=quat).inverse() @ SO3(wxyz=cfg.data.xquat[eid])).log())
    )
    assert pos_err < 0.01
    assert ori_err < 0.01
```

- [ ] **Step 3: Run the tests to verify they FAIL on the current 5-DOF arm**

Run: `uv run pytest tests/test_ik_replay.py -k "tolerance or out or full_pose" -v`
Expected: FAIL — `test_tracks_wrist_within_tolerance` fails (`len(row) == 6` is False, current arm gives 5); `test_cli_replay_ik_out` fails (no `q5` column); `test_arm_reaches_full_pose` fails (`ori_err` ≈ large — the 5-DOF arm cannot reach the non-identity orientation, so `ori_err < 0.01` is False).

- [ ] **Step 4: Replace the arm MJCF**

Overwrite `src/htdp/replay/assets/arm.xml` with exactly:

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

- [ ] **Step 5: Run the targeted tests to verify they PASS**

Run: `uv run pytest tests/test_ik_replay.py -k "tolerance or out or full_pose" -v`
Expected: PASS — joint rows are length 6, the CSV has `q5`, and `test_arm_reaches_full_pose` passes (`pos_err`/`ori_err` ≈ 0).

- [ ] **Step 6: Run the full IK file to confirm no regression**

Run: `uv run pytest tests/test_ik_replay.py tests/test_ik_export.py tests/test_load_pose.py -v`
Expected: ALL pass, 0 skipped (mink present). `test_deterministic`, `test_orientation_recorded_at_zero_cost`, `test_orientation_cost_runs_and_is_deterministic` still pass; writer/load-pose tests unaffected.

- [ ] **Step 7: Full gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pytest`
Expected: all pass. (No mypy line — `replay/` is outside the mypy gate.) If `ruff format --check` fails on the test file, run `uv run ruff format tests/test_ik_replay.py` and re-run.

- [ ] **Step 8: Commit**

```bash
git add src/htdp/replay/assets/arm.xml tests/test_ik_replay.py
git commit -m "feat(replay): upgrade vendored arm to 6-DOF for full-pose IK"
```

---

### Task 2: Docs

**Files:**
- Modify: `docs/ARCHITECTURE.md` (lines ~54, ~58: "5-DOF" → "6-DOF")
- Modify: `AGENTS.md` (line ~66: "5-DOF arm" wording)
- Modify: `docs/ROADMAP.md` (line ~18: "vendored 5-DOF arm")

**Interfaces:** none (docs only).

- [ ] **Step 1: Find the 5-DOF references**

Run: `grep -rn "5-DOF" docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md`
Expected: matches in all three files.

- [ ] **Step 2: Update the wording**

In each match, change "5-DOF" to "6-DOF". In `docs/ARCHITECTURE.md` line ~58 and `AGENTS.md` line ~66, also soften the orientation phrasing: the 6-DOF arm tracks full pose, so replace "best-effort wrist-orientation tracking on the 5-DOF arm" with "wrist-orientation tracking (full 6-DOF pose on the 6-DOF arm)". In `docs/ROADMAP.md` line ~18, note the arm is now a 6-DOF arm capable of full-pose orientation tracking. Keep wording consistent with each file's existing style.

- [ ] **Step 3: Verify no stale 5-DOF wording remains**

Run: `grep -rn "5-DOF\|best-effort" docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md`
Expected: no matches (all updated).

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md
git commit -m "docs(replay): describe the 6-DOF arm + full-pose orientation"
```

---

## Self-Review

**1. Spec coverage:**
- Replace `arm.xml` 5-DOF → 6-DOF (exact MJCF) → Task 1 Step 4. ✅
- No code change to ik/cli/player (asset-only) → no task touches them; constraints state it. ✅
- Joint-count assertions 5→6 (`len==6`, q-cols `q0..q5`) → Task 1 Steps 1. ✅
- New demonstrative full-pose test (non-identity target, `pos_err`/`ori_err < 0.01`) → Task 1 Step 2. ✅
- Position tolerance preserved (`max_error < 0.05`, verified 0.0) → unchanged assertion in `test_tracks_wrist_within_tolerance`, confirmed Step 6. ✅
- Determinism / orientation tests still pass → Task 1 Step 6 runs them. ✅
- Offline/lightweight (no fetch/meshes) → constraints; the MJCF is primitive-geom only. ✅
- Docs "5-DOF" → "6-DOF" in three files → Task 2. ✅
- No new dep/module/schema → no JSON-Schema task. ✅

**2. Placeholder scan:** No TBD/TODO; the full MJCF and full test code are inline; every command lists expected output. ✅

**3. Type consistency:** The new test uses the verified mink names (`mink.Configuration`, `mink.FrameTask`, `mink.solve_ik`, `mink.ConfigurationLimit`, `SE3.from_rotation_and_translation`, `SO3(wxyz=...)`, `cfg.data.xquat`) — matching slice-15 `ik.py` usage exactly. It imports `mink` explicitly (the module's `importorskip("mink")` does not bind the name). `_ARM_XML` is imported from `htdp.replay.ik` (a `Path`, no mink needed to import). Body name `eef` and joint count 6 are consistent between the MJCF and the assertions. ✅
