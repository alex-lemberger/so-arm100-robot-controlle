"""Shared Isaac replay loop: apply a converted joint trajectory frame-by-frame
through the robot's physics-based position drives and read back what was
actually reached. Used by both scripts/replay_episode.py (Task 5/6) and
scripts/generate_synthetic.py (Task 9) so "commanded target -> physics ->
actual joint state" has exactly one implementation.

Isaac-specific (Rule 5) -- only import from a script that already booted
Isaac's own Python interpreter.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from isaacsim.core.utils.types import ArticulationAction


def settle_to_first_frame(
    world, robot, reorder: np.ndarray, first_action: np.ndarray, settle_steps: int, render: bool = False
) -> float:
    """Hold `first_action` for `settle_steps` physics steps so the arm converges from
    its reset pose to the episode's actual starting pose before measured replay begins.
    Returns the max joint error remaining after settling."""
    settle_target = np.zeros(len(robot.dof_names), dtype=np.float32)
    settle_target[reorder] = first_action
    for _ in range(settle_steps):
        robot.apply_action(ArticulationAction(joint_positions=settle_target))
        world.step(render=render)
    return float(np.max(np.abs(robot.get_joint_positions()[reorder] - first_action)))


def run_replay(
    world,
    robot,
    reorder: np.ndarray,
    timesteps: list,
    render: bool = False,
    frame_callback: Callable[[int], None] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply timesteps[i].action frame-by-frame. Returns (commanded_log, actual_log),
    each shape [len(timesteps), 6]. `frame_callback(step_idx)` runs after each step
    (used for optional camera capture in replay_episode.py)."""
    n = len(timesteps)
    commanded_log = np.zeros((n, 6), dtype=np.float64)
    actual_log = np.zeros((n, 6), dtype=np.float64)
    for step_idx, ts in enumerate(timesteps):
        target = np.zeros(len(robot.dof_names), dtype=np.float32)
        target[reorder] = ts.action
        robot.apply_action(ArticulationAction(joint_positions=target))
        world.step(render=render)

        commanded_log[step_idx] = ts.action
        actual_log[step_idx] = robot.get_joint_positions()[reorder]

        if frame_callback is not None:
            frame_callback(step_idx)

    return commanded_log, actual_log
