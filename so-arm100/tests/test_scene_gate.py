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
    SCENE_SOURCE_FILES,
    check_geometry,
    config_fingerprint,
    gate_status,
    require_gate,
    scene_fingerprint,
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


def test_editing_the_builder_invalidates_approval():
    """The hole this closes: the board was rebuilt on 2026-08-16 -- pockets cut, pieces
    reshaped and reseated, knob materials rebound -- entirely in scene_setup.py, with
    simulation.yaml's geometry untouched in the parts that mattered. A config-only
    fingerprint would have carried the old approval straight across it."""
    ok = True
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cfg_path = td / "simulation.yaml"
        cfg_path.write_text(yaml.safe_dump(CFG))
        builder = td / "scene_setup.py"
        builder.write_text("def build_scene(world, cfg):\n    pass\n")
        gate_path = td / "scene_gate.json"
        sources = [builder]

        write_gate(cfg_path, gate_path, [{"name": "x", "ok": True, "detail": ""}],
                   "ref.png", "cmp.png", "tester", source_files=sources)
        good, why = gate_status(cfg_path, gate_path)
        ok &= check("approved scene passes", good, why)

        # The config is untouched; only the code that builds the scene moved.
        before = cfg_path.read_bytes()
        builder.write_text("def build_scene(world, cfg):\n    return 'a different board'\n")
        good, why = gate_status(cfg_path, gate_path)
        ok &= check("editing the builder invalidates approval", not good, why)
        ok &= check("and the reason says the config was untouched", "untouched" in why, why)
        ok &= check("the config really did not change", cfg_path.read_bytes() == before)

        # Even a comment-only edit: we cannot tell which edits change pixels.
        write_gate(cfg_path, gate_path, [{"name": "x", "ok": True, "detail": ""}],
                   "ref.png", "cmp.png", "tester", source_files=sources)
        builder.write_text(builder.read_text() + "# a comment\n")
        good, _ = gate_status(cfg_path, gate_path)
        ok &= check("a comment-only builder edit also invalidates", not good)
    return ok


def test_pre_2026_08_16_approvals_are_stale():
    """A record with no scene_sha256 attests to a config only. It must not pass."""
    ok = True
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cfg_path = td / "simulation.yaml"
        cfg_path.write_text(yaml.safe_dump(CFG))
        gate_path = td / "scene_gate.json"
        gate_path.write_text(json.dumps({
            "config": str(cfg_path),
            "config_sha256": config_fingerprint(cfg_path),   # config matches exactly
            "approved_by": "someone", "approved_at": "2026-08-15T00:00:00+00:00",
            "findings": [{"name": "x", "ok": True, "detail": ""}],
        }))
        good, why = gate_status(cfg_path, gate_path)
        ok &= check("an old config-only approval is refused", not good, why)
        ok &= check("and it says why", "predates" in why, why)
    return ok


def test_the_real_builder_is_fingerprinted():
    """The declared sources must exist, and the fingerprint must actually depend on
    them -- a typo'd path that silently hashed nothing would be the same hole again."""
    ok = True
    for rel in SCENE_SOURCE_FILES:
        ok &= check(f"{rel} exists", (ROOT / rel).exists())
    base = scene_fingerprint(ROOT / "configs" / "simulation.yaml")
    with tempfile.TemporaryDirectory() as td:
        alt = Path(td) / "scene_setup.py"
        alt.write_text("# not the real builder\n")
        other = scene_fingerprint(ROOT / "configs" / "simulation.yaml", [alt])
    ok &= check("the fingerprint depends on the builder's contents", base != other)
    return ok


if __name__ == "__main__":
    results = {}
    for fn in (test_current_scene_passes_geometry,
               test_catches_the_dataset_c_defects,
               test_gate_requires_approval_and_tracks_the_config,
               test_editing_the_builder_invalidates_approval,
               test_pre_2026_08_16_approvals_are_stale,
               test_the_real_builder_is_fingerprinted):
        print(f"\n{fn.__name__}:")
        results[fn.__name__] = fn()
    failed = [k for k, v in results.items() if not v]
    print("\n" + ("ALL PASS" if not failed else f"FAILED: {failed}"))
    sys.exit(1 if failed else 0)
