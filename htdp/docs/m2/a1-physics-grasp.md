# M2.5 A1 — Physics-Grasp Rollout (result)

**Done:** Scripted teacher picks and places the cube under true MuJoCo physics
(`mj_step` + position-servo actuators) with a **friction grasp** — no `qpos`
overwrite, no kinematic attach. Replaces the M1/M2 kinematic shortcut for the
sim loop.

**Scene:** `task_scene_physics.xml` — cube on collision bit 0 (collides with
fingers), friction raised, grasp weld left inactive.
**Driver:** `htdp.replay.physics_episode.run_physics_episode` — drives `data.ctrl`,
opens/closes the gripper, seats the grip for `grip_settle` steps before lifting.

**Gate:** `test_physics_pick_and_place_succeeds` — lifted and place_error < 0.05 m.

**Robustness (3-position sanity check):**

| cube_xy         | lifted | place_err (m) |
|-----------------|--------|---------------|
| (0.46, -0.18)   | False  | 0.344         |
| (0.50, -0.15)   | True   | 0.005         |
| (0.54, -0.12)   | True   | 0.010         |

Corner (0.46, -0.18) fails — the gripper does not achieve a reliable friction
grasp at that offset. A2 demo generation will restrict the cube region to the
confirmed success zone (≈ centre and positive-x corner); the failing corner is
excluded rather than over-tuned.

**Next (A2):** regenerate LeRobot demos from this physics teacher; finger width now
varies, so it returns to the observation (reverses the M2 constant-feature drop).
