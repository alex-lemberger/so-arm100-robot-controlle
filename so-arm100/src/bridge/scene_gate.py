"""Refuse to generate synthetic data from a scene nobody has checked against reality.

Why this exists
---------------
Dataset C (100 synthetic episodes, a 110-episode training set, a 30k-step run and
20 hardware trials) was generated from a scene that had **no board in it at all**,
with the peg placed off the robot's side rather than in front of it, on dimensions
the config itself described as "eyeballed... NOT yet measured".

None of that failed a check, because no check depended on it. Motion is replayed
rather than re-planned (Rule 4), so nothing in the pipeline ever needs the
insertion target to exist -- 100/100 episodes "succeeded" with a healthy mean EE
error. The replay gate that was passed (<10mm) only measures whether joint
trajectories replay faithfully; a robot replaying joints in an empty void scores
perfectly on it.

The one check that would have caught all of it in seconds -- put the render next
to a real frame and look -- was never run. This module makes that check a
precondition instead of an intention.

How the gate works
------------------
`scripts/check_scene_gate.py` renders the scene, runs the automated checks below,
and writes a side-by-side against a real reference frame. A human looks at that
image and re-runs with `--approve`, which records the approval **together with a
fingerprint of configs/simulation.yaml**. Any edit to the scene config changes the
fingerprint and invalidates the approval, so a changed scene has to be looked at
again. That is deliberate: the previous failure was not that the risk was unknown,
it was that a written caveat felt like handling it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GATE_PATH = Path("data/evaluation/scene_gate.json")


def config_fingerprint(config_path: str | Path) -> str:
    """SHA-256 of the scene config's bytes. Any edit invalidates the approval."""
    return hashlib.sha256(Path(config_path).read_bytes()).hexdigest()


@dataclass
class GeometryFinding:
    name: str
    ok: bool
    detail: str


def check_geometry(scene_cfg: dict) -> list[GeometryFinding]:
    """World-space sanity checks that need no renderer.

    These encode the errors actually made, so that each one is caught by name
    rather than by someone happening to notice.
    """
    out: list[GeometryFinding] = []

    board = scene_cfg.get("board")
    if board is None:
        out.append(GeometryFinding("board_exists", False,
                                   "no `board` section -- the insertion target is missing entirely, "
                                   "which is exactly the Dataset C defect"))
        return out
    out.append(GeometryFinding("board_exists", True, "board section present"))

    bx, by, _bz = board["position"]
    # The SO-ARM100 USD faces -Y: at zero pose the gripper sits at y in
    # [-0.257, -0.135]. A board at +x is beside the robot, not in front of it.
    out.append(GeometryFinding(
        "board_in_front_of_robot", by < 0,
        f"board centre y={by:+.3f} (must be negative; the robot faces -Y)"))
    reach = (bx**2 + by**2) ** 0.5
    out.append(GeometryFinding(
        "board_within_reach", 0.10 < reach < 0.40,
        f"board centre {reach:.3f}m from base (EE cluster measured at 0.23-0.30m)"))
    out.append(GeometryFinding(
        "board_has_recesses", bool(board.get("recesses")),
        f"{len(board.get('recesses', []))} recesses defined"))

    obj = scene_cfg.get("object")
    if obj is None:
        out.append(GeometryFinding("object_exists", False, "no `object` section"))
        return out

    px, py, pz = obj["position"]
    r = obj.get("radius", 0.0)
    h = obj.get("height", 0.0)
    hx, hy, hz = [v / 2 for v in board["size"]]
    xy_clear = (px + r < bx - hx or px - r > bx + hx
                or py + r < by - hy or py - r > by + hy)
    z_clear = (pz + h / 2 < _bz - hz) or (pz - h / 2 > _bz + hz)
    out.append(GeometryFinding(
        "peg_clear_of_board", xy_clear or z_clear,
        f"peg ({px:+.3f}, {py:+.3f}) r={r} vs board "
        f"x[{bx-hx:+.3f},{bx+hx:+.3f}] y[{by-hy:+.3f},{by+hy:+.3f}] -- "
        "overlapping spawns the two interpenetrating"))
    preach = (px**2 + py**2) ** 0.5
    out.append(GeometryFinding(
        "peg_within_reach", 0.10 < preach < 0.40,
        f"peg {preach:.3f}m from base"))

    return out


def write_gate(config_path: str | Path, gate_path: str | Path, findings: list[dict],
               reference_frame: str, comparison_image: str, approved_by: str) -> dict:
    from datetime import datetime, timezone

    record = {
        "config": str(config_path),
        "config_sha256": config_fingerprint(config_path),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": approved_by,
        "reference_frame": reference_frame,
        "comparison_image": comparison_image,
        "findings": findings,
    }
    gate_path = Path(gate_path)
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(json.dumps(record, indent=2) + "\n")
    return record


def gate_status(config_path: str | Path, gate_path: str | Path = DEFAULT_GATE_PATH) -> tuple[bool, str]:
    """(ok, reason). Never raises -- callers decide how loudly to fail."""
    gate_path = Path(gate_path)
    if not gate_path.exists():
        return False, f"no scene gate at {gate_path} -- the scene has never been checked against a real frame"
    try:
        record = json.loads(gate_path.read_text())
    except json.JSONDecodeError as exc:
        return False, f"scene gate at {gate_path} is unreadable ({exc})"

    current = config_fingerprint(config_path)
    if record.get("config_sha256") != current:
        return False, (
            f"{config_path} has changed since the scene was approved "
            f"({record.get('config_sha256', '?')[:12]} -> {current[:12]}). "
            "The approval covers the scene that was looked at, not this one."
        )
    failed = [f["name"] for f in record.get("findings", []) if not f.get("ok")]
    if failed:
        return False, f"scene gate recorded failing checks: {', '.join(failed)}"
    return True, (
        f"scene approved by {record.get('approved_by', '?')} at {record.get('approved_at', '?')} "
        f"against {record.get('reference_frame', '?')}"
    )


def require_gate(config_path: str | Path, gate_path: str | Path = DEFAULT_GATE_PATH,
                 override: bool = False) -> str:
    """Raise SystemExit unless the scene has been approved for this exact config.

    `override` exists because a hard block with no escape gets worked around in
    ways that leave no trace. Taking it is recorded in the generated data's
    provenance, so a dataset built from an unchecked scene says so about itself.
    """
    ok, reason = gate_status(config_path, gate_path)
    if ok:
        return reason
    if override:
        return f"SCENE GATE OVERRIDDEN -- {reason}"
    raise SystemExit(
        "\n"
        "=======================================================================\n"
        " SCENE GATE FAILED -- refusing to generate data from an unchecked scene\n"
        "=======================================================================\n"
        f" {reason}\n\n"
        " Dataset C was generated from a scene with no board in it, a peg beside\n"
        " the robot instead of in front of it, and dimensions the config itself\n"
        " called eyeballed. It cost a 30k-step training run and 20 hardware\n"
        " trials, and nothing failed, because nothing checked.\n\n"
        " Run:\n"
        "     ./check_scene_gate.sh\n"
        " look at the side-by-side it writes, then approve it:\n"
        "     ./check_scene_gate.sh --approve <your-name>\n\n"
        " Or pass --skip-scene-gate to proceed anyway; the override is recorded\n"
        " in the output's provenance.\n"
        "=======================================================================\n"
    )
