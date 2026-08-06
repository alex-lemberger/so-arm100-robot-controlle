# src/htdp/learn/rollout.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from htdp.learn.obs import build_observation, build_proprio_observation
from htdp.learn.policy import (
    ACTConfig,
    ACTPolicy,
    VisuomotorACTConfig,
    VisuomotorACTPolicy,
)
from htdp.learn.train import Normalizer, VisuomotorNormalizer

_IMAGE_HW = 96  # visuomotor obs resolution (matches B2 demos / the 'front' camera training data)


@dataclass
class RolloutResult:
    success: bool
    place_error: float
    lifted: bool
    cube_final_xy: tuple[float, float]
    steps: int


def load_policy(ckpt_path: Path) -> tuple[ACTPolicy, Normalizer]:
    ckpt: dict[str, Any] = torch.load(Path(ckpt_path), weights_only=False)
    cfg = ACTConfig(**ckpt["cfg"])
    net = ACTPolicy(cfg)
    net.load_state_dict(ckpt["state_dict"])
    net.eval()
    return net, Normalizer(ckpt["stats"])


_APPROACH_Z = 0.35  # ready-pose height above the table (matches the teacher's _Z_HI)
_Z_LO = 0.225  # cube rest height = table_top(0.20) + cube_half(0.025)
_GRIPPER_OPEN = 255.0  # position-servo gripper ctrl (matches the physics teacher)
_GRIPPER_CLOSE = 0.0


def rollout_policy(
    policy: ACTPolicy,
    normalizer: Normalizer,
    cube_xy: tuple[float, float],
    *,
    exec_horizon: int = 16,
    max_chunks: int = 60,
    settle: int = 20,
    grip_settle: int = 200,
    grasp_thresh: float = 0.5,
) -> RolloutResult:
    """Closed-loop PHYSICS rollout. The policy's joint targets drive the position-servo actuators
    under ``mj_step`` (consistent with the A2 physics teacher), re-planning every ``exec_horizon``
    actions (receding horizon). Grasp is a TRUE friction grasp — the gripper ctrl is closed on the
    policy's gripper command and the cube is held by finger contact, NOT a kinematic attach. On the
    open->close transition the grip is seated for ``grip_settle`` extra steps before the arm moves
    on, exactly as the teacher seats it. The arm resets to an in-distribution ready pose above the
    cube via IK, fingers open.
    """
    import mujoco

    from htdp.replay.arm_ik import solve_arm_ik
    from htdp.replay.scene import OBJECT_FREEJOINT, TARGET_SITE, TASK_SCENE_PHYSICS_XML

    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))
    data = mujoco.MjData(model)
    key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
    mujoco.mj_resetDataKeyframe(model, data, key)
    grasp_sid: int = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "grasp_site")
    cube_jid: int = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, OBJECT_FREEJOINT)
    cube_qadr: int = int(model.jnt_qposadr[cube_jid])
    tgt: np.ndarray = model.site(TARGET_SITE).pos

    # Seat the cube on the table (full 7-DOF freejoint: the home keyframe zeroes it otherwise).
    data.qpos[cube_qadr : cube_qadr + 3] = (cube_xy[0], cube_xy[1], _Z_LO)
    data.qpos[cube_qadr + 3 : cube_qadr + 7] = (1.0, 0.0, 0.0, 0.0)

    # Settle into a ready pose above the cube (in-distribution start; the teacher's first frame is
    # also an above-cube IK pose). Drive the actuators there with the gripper open.
    ready = solve_arm_ik([(0.0, cube_xy[0], cube_xy[1], _APPROACH_Z, 1.0, 0.0, 0.0, 0.0)])
    ready_q = ready.joint_trajectory[0][:7]
    data.ctrl[:7] = ready_q
    data.ctrl[7] = _GRIPPER_OPEN
    for _ in range(grip_settle):
        mujoco.mj_step(model, data)
    start_z = float(data.body("cube").xpos[2])

    lifted = False
    steps = 0
    prev_closed = False
    for _ in range(max_chunks):
        obs = build_observation(model, data, grasp_sid)
        obs_t = normalizer.normalize_obs(torch.as_tensor(obs))
        chunk = normalizer.denormalize_action(policy.act(obs_t)).detach().numpy()
        for action in chunk[:exec_horizon]:
            closed = float(action[7]) > grasp_thresh
            data.ctrl[:7] = action[:7]
            data.ctrl[7] = _GRIPPER_CLOSE if closed else _GRIPPER_OPEN
            # Seat the grip on the open->close transition, exactly like the teacher.
            n = settle + (grip_settle if closed and not prev_closed else 0)
            for _ in range(n):
                mujoco.mj_step(model, data)
                steps += 1
                if float(data.body("cube").xpos[2]) > start_z + 0.05:
                    lifted = True
            prev_closed = closed

    cube: np.ndarray = data.body("cube").xpos
    place_error = float(np.hypot(cube[0] - tgt[0], cube[1] - tgt[1]))
    success = bool(place_error < 0.05 and lifted)
    return RolloutResult(success, place_error, lifted, (float(cube[0]), float(cube[1])), steps)


def load_visuomotor_policy(ckpt_path: Path):  # type: ignore[no-untyped-def]
    ckpt = torch.load(Path(ckpt_path), weights_only=False)
    net = VisuomotorACTPolicy(VisuomotorACTConfig(**ckpt["cfg"]))
    net.load_state_dict(ckpt["state_dict"])
    net.eval()
    return net, VisuomotorNormalizer(ckpt["proprio_stats"], ckpt["action_stats"])


def rollout_visuomotor_policy(
    policy: VisuomotorACTPolicy,
    normalizer: VisuomotorNormalizer,
    cube_xy: tuple[float, float],
    *,
    exec_horizon: int = 16,
    max_chunks: int = 60,
    settle: int = 20,
    grip_settle: int = 200,
    grasp_thresh: float = 0.5,
    video_out: "Path | None" = None,
    video_fps: int = 30,
    domain_randomize: bool = False,
    dr_seed: int = 0,
) -> RolloutResult:
    """Closed-loop VISUOMOTOR physics rollout. Same true-physics actuator/friction-grasp loop as
    ``rollout_policy``, but the policy sees only the ``front`` camera image + proprioception — the
    cube and target positions are NOT provided; the CNN must localise them from pixels. The frame
    is rendered through the same ``render_camera`` path the B2 demos used, so train/rollout framing
    cannot drift. If ``video_out`` is given, a 480x640 ``front`` view is also captured once per
    executed action and written as an MP4 (separate from the 96x96 policy input).

    If ``domain_randomize``, the episode's own scene is perturbed once via
    ``domain_randomization.randomize_scene`` (seeded by ``dr_seed``) before rollout — used to
    report the C1 robustness number under novel lighting/table/camera/cube-friction shift
    (docs/m2/c1-domain-randomization-scope.md). Default off so the canonical B3 numbers/gates
    don't shift silently.
    """
    import mujoco

    from htdp.replay.arm_ik import solve_arm_ik
    from htdp.replay.render import render_camera
    from htdp.replay.scene import OBJECT_FREEJOINT, TARGET_SITE, TASK_SCENE_PHYSICS_XML

    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))
    if domain_randomize:
        from htdp.replay.domain_randomization import randomize_scene

        randomize_scene(model, np.random.default_rng(dr_seed), None)
    data = mujoco.MjData(model)
    key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
    mujoco.mj_resetDataKeyframe(model, data, key)
    grasp_sid: int = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "grasp_site")
    cube_jid: int = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, OBJECT_FREEJOINT)
    cube_qadr: int = int(model.jnt_qposadr[cube_jid])
    tgt: np.ndarray = model.site(TARGET_SITE).pos
    renderer = mujoco.Renderer(model, height=_IMAGE_HW, width=_IMAGE_HW)
    video_renderer = mujoco.Renderer(model, height=480, width=640) if video_out else None
    video_frames: list[np.ndarray] = []

    data.qpos[cube_qadr : cube_qadr + 3] = (cube_xy[0], cube_xy[1], _Z_LO)
    data.qpos[cube_qadr + 3 : cube_qadr + 7] = (1.0, 0.0, 0.0, 0.0)

    ready = solve_arm_ik([(0.0, cube_xy[0], cube_xy[1], _APPROACH_Z, 1.0, 0.0, 0.0, 0.0)])
    data.ctrl[:7] = ready.joint_trajectory[0][:7]
    data.ctrl[7] = _GRIPPER_OPEN
    for _ in range(grip_settle):
        mujoco.mj_step(model, data)
    start_z = float(data.body("cube").xpos[2])

    lifted = False
    steps = 0
    prev_closed = False
    for _ in range(max_chunks):
        proprio = build_proprio_observation(model, data, grasp_sid)
        prop_t = normalizer.normalize_proprio(torch.as_tensor(proprio))
        img = render_camera(
            model, data, camera="front", height=_IMAGE_HW, width=_IMAGE_HW, renderer=renderer
        )
        img_t = torch.as_tensor(np.ascontiguousarray(img)).float().div(255.0).permute(2, 0, 1)
        chunk = normalizer.denormalize_action(policy.act(img_t, prop_t)).detach().numpy()
        for action in chunk[:exec_horizon]:
            closed = float(action[7]) > grasp_thresh
            data.ctrl[:7] = action[:7]
            data.ctrl[7] = _GRIPPER_CLOSE if closed else _GRIPPER_OPEN
            n = settle + (grip_settle if closed and not prev_closed else 0)
            for _ in range(n):
                mujoco.mj_step(model, data)
                steps += 1
                if float(data.body("cube").xpos[2]) > start_z + 0.05:
                    lifted = True
            prev_closed = closed
            if video_renderer is not None:
                video_renderer.update_scene(data, camera="front")
                video_frames.append(video_renderer.render())

    renderer.close()
    if video_renderer is not None:
        import imageio.v3 as iio  # type: ignore[import-not-found]

        video_renderer.close()
        out = Path(video_out)  # type: ignore[arg-type]
        out.parent.mkdir(parents=True, exist_ok=True)
        iio.imwrite(out, video_frames, fps=video_fps, codec="libx264")
    cube: np.ndarray = data.body("cube").xpos
    place_error = float(np.hypot(cube[0] - tgt[0], cube[1] - tgt[1]))
    success = bool(place_error < 0.05 and lifted)
    return RolloutResult(success, place_error, lifted, (float(cube[0]), float(cube[1])), steps)
