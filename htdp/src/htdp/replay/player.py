from __future__ import annotations

from pathlib import Path

import polars as pl


class ReplayUnavailable(RuntimeError):
    """Raised when MuJoCo is not installed."""


_TRACKERS = ("right_wrist", "left_wrist", "torso", "object")


def load_release_motion(
    release_dir: Path,
) -> dict[str, list[tuple[float, float, float, float]]]:
    out: dict[str, list[tuple[float, float, float, float]]] = {}
    sessions = sorted((release_dir / "data").iterdir())
    sid = sessions[0].name
    for tracker in _TRACKERS:
        df = pl.read_csv(release_dir / "data" / sid / "streams" / f"motion_{tracker}.csv")
        out[tracker] = [
            (r["timestamp_s"], r["x_m"], r["y_m"], r["z_m"]) for r in df.iter_rows(named=True)
        ]
    return out


def load_release_pose(
    release_dir: Path,
) -> dict[str, list[tuple[float, float, float, float, float, float, float, float]]]:
    out: dict[str, list[tuple[float, float, float, float, float, float, float, float]]] = {}
    sessions = sorted((release_dir / "data").iterdir())
    sid = sessions[0].name
    for tracker in _TRACKERS:
        df = pl.read_csv(release_dir / "data" / sid / "streams" / f"motion_{tracker}.csv")
        out[tracker] = [
            (r["timestamp_s"], r["x_m"], r["y_m"], r["z_m"], r["qw"], r["qx"], r["qy"], r["qz"])
            for r in df.iter_rows(named=True)
        ]
    return out


def _model_xml() -> str:
    bodies = "\n".join(
        f'<body name="{t}" mocap="true" pos="0 0 1">'
        f'<geom type="sphere" size="0.03" rgba="0.2 0.6 1 1"/></body>'
        for t in _TRACKERS
    )
    return f"<mujoco><worldbody>{bodies}</worldbody></mujoco>"


def replay_release(
    release_dir: Path,
    headless: bool = True,
    max_steps: int = 50,
) -> int:
    try:
        import mujoco  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise ReplayUnavailable("install with: uv sync --extra replay") from exc

    motion = load_release_motion(release_dir)
    model = mujoco.MjModel.from_xml_string(_model_xml())
    data = mujoco.MjData(model)
    n = min(max_steps, min(len(v) for v in motion.values()))
    for i in range(n):
        for j, tracker in enumerate(_TRACKERS):
            _, x, y, z = motion[tracker][i]
            data.mocap_pos[j] = [x, y, z]
        mujoco.mj_step(model, data)
    return n
