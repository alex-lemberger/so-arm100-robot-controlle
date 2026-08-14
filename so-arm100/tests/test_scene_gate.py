"""Checks for the scene gate's pure logic (no Isaac, no renderer).

    docker run --rm -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" lerobot-train:latest \
        python3 tests/test_scene_gate.py
"""

import copy
import json
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bridge.scene_gate import (  # noqa: E402
    check_geometry,
    config_fingerprint,
    gate_status,
    require_gate,
    write_gate,
)

CFG = yaml.safe_load((ROOT / "configs" / "simulation.yaml").read_text())


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  -- ' + detail if detail and not cond else ''}")
    return cond


def _findings(cfg):
    return {f.name: f.ok for f in check_geometry(cfg)}


def test_current_scene_passes_geometry():
    r = _findings(CFG)
    ok = True
    for name, passed in r.items():
        ok &= check(f"current scene: {name}", passed)
    return ok


def test_catches_the_dataset_c_defects():
    """Each historical mistake must fail by name, not by someone noticing."""
    ok = True

    no_board = {k: v for k, v in CFG.items() if k != "board"}
    ok &= check("missing board is caught", _findings(no_board).get("board_exists") is False)

    beside = copy.deepcopy(CFG)
    beside["board"]["position"] = [0.22, 0.08, 0.005]      # the original guess: +x, beside the robot
    ok &= check("board beside the robot is caught", _findings(beside)["board_in_front_of_robot"] is False)

    far = copy.deepcopy(CFG)
    far["board"]["position"] = [0.0, -0.9, 0.005]
    ok &= check("board out of reach is caught", _findings(far)["board_within_reach"] is False)

    overlap = copy.deepcopy(CFG)
    overlap["object"]["position"] = [0.0, -0.20, 0.014]     # inside the board footprint
    ok &= check("peg inside the board is caught", _findings(overlap)["peg_clear_of_board"] is False)

    bare = copy.deepcopy(CFG)
    bare["board"]["recesses"] = []
    ok &= check("board with no recesses is caught", _findings(bare)["board_has_recesses"] is False)
    return ok


def test_gate_requires_approval_and_tracks_the_config():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cfg_path = td / "simulation.yaml"
        cfg_path.write_text(yaml.safe_dump(CFG))
        gate_path = td / "scene_gate.json"

        good, why = gate_status(cfg_path, gate_path)
        ok &= check("unapproved scene is refused", not good, why)
        try:
            require_gate(cfg_path, gate_path)
            ok &= check("require_gate raises when unapproved", False)
        except SystemExit:
            ok &= check("require_gate raises when unapproved", True)

        write_gate(cfg_path, gate_path, [{"name": "x", "ok": True, "detail": ""}],
                   "ref.png", "cmp.png", "tester")
        good, why = gate_status(cfg_path, gate_path)
        ok &= check("approved scene passes", good, why)

        # The whole point: editing the scene invalidates the approval.
        edited = copy.deepcopy(CFG)
        edited["board"]["position"] = [0.0, -0.25, 0.005]
        cfg_path.write_text(yaml.safe_dump(edited))
        good, why = gate_status(cfg_path, gate_path)
        ok &= check("editing the config invalidates approval", not good, why)

        note = require_gate(cfg_path, gate_path, override=True)
        ok &= check("override is allowed but says so", "OVERRIDDEN" in note, note)

        # A gate recording failed checks must not count as approval.
        write_gate(cfg_path, gate_path, [{"name": "board_exists", "ok": False, "detail": ""}],
                   "ref.png", "cmp.png", "tester")
        good, why = gate_status(cfg_path, gate_path)
        ok &= check("gate with failing checks is refused", not good, why)

        ok &= check("fingerprint changes with content",
                    config_fingerprint(cfg_path) != config_fingerprint(ROOT / "configs" / "simulation.yaml"))
    return ok


if __name__ == "__main__":
    results = {}
    for fn in (test_current_scene_passes_geometry,
               test_catches_the_dataset_c_defects,
               test_gate_requires_approval_and_tracks_the_config):
        print(f"\n{fn.__name__}:")
        results[fn.__name__] = fn()
    failed = [k for k, v in results.items() if not v]
    print("\n" + ("ALL PASS" if not failed else f"FAILED: {failed}"))
    sys.exit(1 if failed else 0)
