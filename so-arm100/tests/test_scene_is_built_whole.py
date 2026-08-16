"""Refuse to let a script build half the scene.

Until 2026-08-16 `scripts/export_lerobot_dataset.py` -- the script that renders the
pixels a policy actually trains on -- called `add_table_and_object` and `add_lighting`
and never called `add_board`. So every synthetic frame it ever exported showed the peg
with nothing to insert it into, while `scripts/generate_synthetic.py` simulated those
same episodes with a board present. Nothing failed. The scene gate passed throughout,
because the gate renders its OWN scene: it built the board correctly, looked right,
and then approved a config -- attesting to a scene the exporter never built.

That is the Dataset C defect (see src/bridge/scene_gate.py) recurring one script over,
and no amount of care in the gate can catch it, because the gate cannot see what
another script assembles. The fix is structural: `scene_setup.build_scene` is the only
way to put the scene into a World, and this test fails if anything reaches past it.

Pure text inspection -- no Isaac, so it runs in the normal test image.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARTIAL = {"add_table_and_object", "add_board", "add_lighting"}

# scene_setup.py defines them; smoke_board_isaac.py is the unit smoke test for
# add_board itself, which is the one legitimate reason to call it directly.
EXEMPT = {
    ROOT / "src" / "isaac" / "scene_setup.py",
    ROOT / "tests" / "smoke_board_isaac.py",
}
# replay_episode.py falls back to add_lighting ONLY when there is no scene config at
# all (a bare-robot replay, which predates the scene and must stay reproducible).
ALLOWED_FALLBACK = {ROOT / "scripts" / "replay_episode.py": {"add_lighting"}}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  -- ' + detail if detail and not cond else ''}")
    return cond


def _called_names(tree):
    return {n.func.id for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def _sources():
    for d in ("scripts", "tests", "src"):
        for path in sorted((ROOT / d).rglob("*.py")):
            if path not in EXEMPT:
                yield path


def test_no_script_builds_the_scene_piecemeal():
    ok = True
    for path in _sources():
        called = _called_names(ast.parse(path.read_text()))
        offenders = (called & PARTIAL) - ALLOWED_FALLBACK.get(path, set())
        ok &= check(f"{path.relative_to(ROOT)} does not assemble the scene by hand",
                    not offenders,
                    f"calls {sorted(offenders)} directly; use scene_setup.build_scene")
    return ok


def test_every_rendering_path_builds_the_scene():
    """Anything that creates a camera renders pixels, and pixels that go anywhere near
    training or a human's judgement have to show the whole scene.

    Entry points only -- src/isaac/camera_capture.py is where create_camera is DEFINED;
    it has no World to build a scene into."""
    ok = True
    for path in _sources():
        if path.parts[-2] not in ("scripts", "tests"):
            continue
        src = path.read_text()
        if "create_camera" not in src and "create_tracked_camera" not in src:
            continue
        ok &= check(f"{path.relative_to(ROOT)} renders through build_scene",
                    "build_scene" in src,
                    "creates a camera but never calls build_scene")
    return ok


def test_build_scene_adds_all_three():
    """The builder itself must still call all three, or the guard above is vacuous."""
    tree = ast.parse((ROOT / "src" / "isaac" / "scene_setup.py").read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "build_scene")
    called = _called_names(fn)
    return check("build_scene calls table, board and lighting", PARTIAL <= called,
                 f"missing {sorted(PARTIAL - called)}")


def test_the_guard_would_have_caught_the_original_bug():
    """A guard nobody has seen fail is not known to work. This is the exporter's own
    scene construction as it stood on 2026-08-15 -- table and lights, no board."""
    was_broken = """
from isaac.scene_setup import add_lighting, add_table_and_object, load_scene_config
scene_object, scene_material = add_table_and_object(world, scene_cfg)
lights = add_lighting(scene_cfg)
camera = create_camera(pos, target)
"""
    called = _called_names(ast.parse(was_broken))
    ok = check("the 2026-08-15 exporter trips the piecemeal check", bool(called & PARTIAL),
               f"called {sorted(called)}")
    ok &= check("and it never mentions build_scene", "build_scene" not in was_broken)
    return ok


if __name__ == "__main__":
    results = {}
    for fn in (test_no_script_builds_the_scene_piecemeal,
               test_every_rendering_path_builds_the_scene,
               test_build_scene_adds_all_three,
               test_the_guard_would_have_caught_the_original_bug):
        print(f"\n{fn.__name__}:")
        results[fn.__name__] = fn()
    failed = [k for k, v in results.items() if not v]
    print("\n" + ("ALL PASS" if not failed else f"FAILED: {failed}"))
    sys.exit(1 if failed else 0)
