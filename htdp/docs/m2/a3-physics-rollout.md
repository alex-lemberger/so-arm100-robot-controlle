# M2.5 A3 — Physics Rollout + Retrain (result)

**Done:** The closed-loop policy rollout and the eval baseline now run under **true physics**
(position-servo actuators + `mj_step` + friction grasp), matching the A2 physics teacher.
The kinematic executor (qpos overwrite + kinematic attach + fingers-held-open) is gone, so
teacher and executor agree again — the M2 "kinematic-vs-physics action mismatch" lesson,
applied in reverse.

## What changed

- `rollout_policy` (`src/htdp/learn/rollout.py`): loads `task_scene_physics.xml`, seats the
  cube on its freejoint, settles into an above-cube ready pose by **driving the actuators**
  (not forcing qpos). Each policy action sets `data.ctrl[:7]` (joint targets) and `data.ctrl[7]`
  (gripper open 255 / close 0, thresholded on the policy's gripper command at 0.5), then steps
  physics. On the open->close transition the grip is **seated for `grip_settle` steps** before
  the arm moves on, exactly like the teacher. The cube is held by **finger friction only** — no
  kinematic attach. Receding horizon unchanged (re-plan every `exec_horizon`).
- `eval.baseline_at`: now runs the **physics** teacher (`run_physics_episode`), so
  policy-vs-baseline is apples-to-apples under the same physics. Success = lifted and
  place_error < 0.05 m.
- `test_policy_beats_zero_on_held_out`: **un-skipped** — it is the end-to-end A3 gate again.

## Result

| executor | success | mean place_error |
|----------|---------|------------------|
| policy (physics rollout) | **4/6 (67%)** | 0.097 m |
| baseline (physics teacher) | 6/6 (100%) | 0.008 m |

(30 train / 6 held-out demos, 2500 train steps, seed 0.)

A non-trivial held-out success under **true contact physics** — no kinematic shortcut anywhere
in the loop. Below the M2 kinematic 100% as predicted: friction-grasp contact compounds small
policy errors (a slightly-off approach slips the grasp), which the kinematic attach used to
paper over. This is the honest number for a state-based ACT policy on a physics friction grasp.

## Gates

Un-skipped end-to-end guard passes; `tests/learn tests/replay` = **25 passed, 0 skipped**.

**Next (Track B):** B1 camera render in the physics scene, B2 image demos, B3 visuomotor ACT
(drop the privileged cube/target xyz from the observation, keep proprioception + pixels).
