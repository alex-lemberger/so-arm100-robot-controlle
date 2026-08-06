"""v1 troweling demo: drive a MuJoCo UR5e end-effector in a zigzag sweep.

This is a *kinematic fake* — the joints are driven by a scripted pattern that
looks like a troweling pass. It proves the sim + control loop. Swap in a real
Cartesian path later via sim/ik.py.

Run:  python sim/zigzag_demo.py

NOTE: scaffolded without MuJoCo installed; not yet executed. Expect to tweak
HOME / amplitudes on first run.
"""
from __future__ import annotations

import time

import numpy as np
import mujoco
import mujoco.viewer

MODEL_PATH = "models/ur5e/scene.xml"

# UR5e position actuators, in order (confirm against models/ur5e/ur5e.xml):
#   0 shoulder_pan  1 shoulder_lift  2 elbow  3 wrist_1  4 wrist_2  5 wrist_3
HOME = np.array([0.0, -1.57, 1.57, -1.57, -1.57, 0.0])

# Troweling pattern (radians / Hz) — tune to taste.
SWEEP_AMP = 0.6    # horizontal pass on the base joint
SWEEP_HZ = 0.15    # slow left <-> right
ZIG_AMP = 0.35     # vertical zigzag on the elbow
ZIG_HZ = 1.2       # faster zigzag within the pass


def troweling_targets(t: float) -> np.ndarray:
    """Joint targets for a fake troweling sweep at time t (seconds)."""
    q = HOME.copy()
    q[0] += SWEEP_AMP * np.sin(2 * np.pi * SWEEP_HZ * t)        # horizontal sweep
    q[2] += ZIG_AMP * np.sin(2 * np.pi * ZIG_HZ * t)           # elbow zigzag
    q[3] += 0.5 * ZIG_AMP * np.sin(2 * np.pi * ZIG_HZ * t)     # wrist follows
    return q


def main() -> None:
    model = mujoco.MjModel.from_xml_path(MODEL_PATH)
    data = mujoco.MjData(model)
    data.ctrl[: model.nu] = HOME[: model.nu]

    with mujoco.viewer.launch_passive(model, data) as viewer:
        start = time.time()
        while viewer.is_running():
            step_start = time.time()
            t = step_start - start
            data.ctrl[: model.nu] = troweling_targets(t)[: model.nu]
            mujoco.mj_step(model, data)
            viewer.sync()
            # real-time pacing
            sleep = model.opt.timestep - (time.time() - step_start)
            if sleep > 0:
                time.sleep(sleep)


if __name__ == "__main__":
    main()
