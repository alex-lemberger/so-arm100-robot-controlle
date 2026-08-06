# M2.5 B1 — Camera Render (result)

**Done:** The physics scene now has a defined camera and a reusable RGB render path — the
visual stream B2 (image demos) and B3 (visuomotor ACT) will consume. B1 is plumbing only: no
observation, policy, or demo changes (clean seam to B2/B3).

## What changed

- **`task_scene_physics.xml`**: a fixed third-person camera `front`
  (`pos="1.15 0 0.55" xyaxes="0 1 0 -0.45 0 0.9"`) framing the table, cube, target and arm.
  Looks from +x down at the workspace centre. `<global offwidth=640 offheight=480>` makes the
  offscreen buffer explicit.
- **`render_camera(model, data, *, camera, height, width)`** (`replay/render.py`): single RGB
  frame `(H, W, 3)` from a NAMED camera at the current physics state. The one path both
  train-time demos and rollout-time pixels go through, so framing can't drift between them.
- **`render_physics_episode(out, cube_xy, *, camera="front", ...)`**: runs the physics
  friction-grasp episode and writes an MP4, capturing one frame per settled IK target via the
  `on_sample` hook (~200 frames).
- **CLI `render-physics`** (`--video --x --y --camera --force`).
- Demo artifact: `docs/demo/m25_physics_pick_place.mp4`.

## Gates

- `test_front_camera_frames_the_cube`: renders from `front` and asserts the red cube's pixels
  are present (> 20). A non-blank frame is not enough — a misaimed camera still renders
  something; this is the render-side analogue of the M1 false-green-video lesson.
- `test_render_physics_episode_writes_nonempty_mp4`: MP4 written, overwrite refused without
  `--force`.
- `tests/replay tests/learn` = 27 passed.

Visual check: the `front` frame shows table centred, red cube left, green target right, Franka
arm above — the whole task in one view.

## Resolution convention (for B2/B3)

`render_camera` is resolution-agnostic via `height`/`width`. Plan: policy obs at **96×96**
(standard IL size), human video at **480×640**. Both come from this one path.

**Next (B2):** write the camera frame into each LeRobot demo row (`observation.image`, 96×96)
alongside the existing state, via `render_camera` in the demo recorder.

**Deferred to B3:** wrist-mounted camera; dropping the privileged cube/target xyz from the
observation; the visuomotor ACT encoder (CNN backbone on the image).
