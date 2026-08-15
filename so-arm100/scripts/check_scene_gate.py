"""Render the sim scene and put it beside a real frame, so someone can look.

See src/bridge/scene_gate.py for why this is a precondition rather than a habit.

    ./check_scene_gate.sh                    # render + check, writes the comparison
    ./check_scene_gate.sh --approve alex     # after looking at it, record approval

Approval is recorded against a fingerprint of configs/simulation.yaml, so editing
the scene invalidates it and the comparison has to be looked at again.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


REPORT_PATH = REPO_ROOT / "scene_gate_report.txt"
_REPORT = None


def say(*a):
    """Isaac's python.sh launcher swallows stdout, so the gate's own report has to
    go to a file or it is invisible -- which for a gate nobody can read is the
    same as not existing."""
    line = " ".join(str(x) for x in a)
    print(line)
    if _REPORT is not None:
        _REPORT.write(line + "\n")
        _REPORT.flush()


def main() -> int:
    global _REPORT
    _REPORT = open(REPORT_PATH, "w", buffering=1)
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene-config", default=str(REPO_ROOT / "configs" / "simulation.yaml"))
    ap.add_argument("--robot-config", default=str(REPO_ROOT / "configs" / "robot_mapping.yaml"))
    ap.add_argument("--reference", default=str(REPO_ROOT / "docs" / "reference" / "board_reference_demo.png"),
                    help="a real overview frame to compare against")
    ap.add_argument("--out", default=str(REPO_ROOT / "scene_gate_comparison.png"))
    ap.add_argument("--gate", default=str(REPO_ROOT / "data" / "evaluation" / "scene_gate.json"))
    ap.add_argument("--approve", metavar="NAME",
                    help="record approval for the CURRENT config after looking at the comparison")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from bridge.scene_gate import check_geometry, config_fingerprint, write_gate  # noqa: E402

    import yaml  # noqa: E402
    scene_cfg = yaml.safe_load(Path(args.scene_config).read_text())

    # Geometry checks first: they need no renderer, and they are what would have
    # caught the Dataset C scene.
    findings = check_geometry(scene_cfg)
    say("\nGeometry checks:")
    for f in findings:
        say(f"  {'PASS' if f.ok else 'FAIL'}  {f.name:26s} {f.detail}")

    from isaacsim import SimulationApp  # noqa: E402
    simulation_app = SimulationApp({"headless": True})

    render_ok = False
    result = 1
    try:
        import numpy as np
        from PIL import Image
        from isaacsim.core.api import World
        from isaacsim.core.api.robots import Robot
        from isaacsim.core.utils.stage import add_reference_to_stage
        import omni.replicator.core as rep

        sys.path.insert(0, str(REPO_ROOT / "src"))
        from isaac.camera_capture import capture_rgb, create_camera, warm_up
        from isaac.scene_setup import add_board, add_lighting, add_table_and_object

        robot_cfg = yaml.safe_load(Path(args.robot_config).read_text())
        world = World(stage_units_in_meters=1.0, physics_dt=1 / 30, rendering_dt=1 / 30)
        add_reference_to_stage(usd_path=robot_cfg["isaac_robot"]["asset_path"], prim_path="/World/so_arm100")
        world.scene.add(Robot(prim_path="/World/so_arm100", name="so_arm100"))
        add_table_and_object(world, scene_cfg)
        add_board(world, scene_cfg)

        # Lit from `lighting:` in the scene config, i.e. the SAME lights
        # scripts/export_lerobot_dataset.py uses. Until 2026-08-15 this rendered at
        # dome 1000 / distant 2500 at a different azimuth while the exporter shipped
        # dome 2000 / distant 20000 -- so the picture a human approved was not lit
        # like the frames that went into training, which is most of what a scene gate
        # is for. If the side-by-side now looks wrong, that is the finding.
        add_lighting(scene_cfg)

        world.reset()

        ref_img = Image.open(args.reference).convert("RGB")
        camera = create_camera(scene_cfg["camera"]["position"], scene_cfg["camera"]["target"],
                               ref_img.size, scene_cfg["camera"].get("focal_length"))
        warm_up(world, camera)
        for _ in range(3):
            world.step(render=True)
            rep.orchestrator.step(rt_subframes=1)
        frame = capture_rgb(camera)

        if frame is None or not frame.size:
            findings.append(_finding("render_produced_pixels", False, "camera returned no data"))
        else:
            sim_img = Image.fromarray(frame[:, :, :3])
            arr = np.asarray(sim_img).astype(float)
            # A blank or single-colour render is the 08-11 failure mode: every
            # individual check passed and the frames came back empty.
            spread = float(arr.std())
            findings.append(_finding("render_produced_pixels", spread > 5.0,
                                     f"pixel std {spread:.1f} (a flat frame means the camera sees nothing)"))
            # Match the render against colours we control, not against a photo.
            found, missing = _recess_colours_visible(arr, scene_cfg)
            findings.append(_finding("board_visible_in_render", not missing,
                                     f"recesses visible: {sorted(found)}"
                                     + (f"; NOT visible: {sorted(missing)}" if missing else "")))

            combo = Image.new("RGB", (ref_img.width * 2, ref_img.height), "black")
            combo.paste(ref_img, (0, 0))
            combo.paste(sim_img.resize(ref_img.size), (ref_img.width, 0))
            combo.save(args.out)
            say(f"\nComparison written to {args.out}  (left: real, right: sim)")
            render_ok = True

        # Everything that matters has to happen BEFORE simulation_app.close():
        # closing the app ends the process, so anything after it never runs. That
        # silently truncated this very report the first time.
        result = _report_and_approve(args, findings, render_ok, write_gate, config_fingerprint)
    finally:
        simulation_app.close()
    return result


def _report_and_approve(args, findings, render_ok, write_gate, config_fingerprint) -> int:
    say("\nAll checks:")
    for f in findings:
        say(f"  {'PASS' if f.ok else 'FAIL'}  {f.name:26s} {f.detail}")
    failed = [f.name for f in findings if not f.ok]

    if args.approve:
        if failed:
            say(f"\nREFUSING to approve: {', '.join(failed)} still failing.")
            return 1
        if not render_ok:
            say("\nREFUSING to approve: no comparison image was produced.")
            return 1
        write_gate(args.scene_config, args.gate,
                   [{"name": f.name, "ok": f.ok, "detail": f.detail} for f in findings],
                   args.reference, args.out, args.approve)
        say(f"\nScene APPROVED by {args.approve} for config "
            f"{config_fingerprint(args.scene_config)[:12]}; gate written to {args.gate}")
        return 0

    if failed:
        say(f"\n{len(failed)} check(s) failing: {', '.join(failed)}")
        return 1
    say("\nAutomated checks pass. Now LOOK at the comparison image -- the automated\n"
        "checks cannot tell you the scene resembles reality, only that it is not\n"
        "obviously empty. Then approve with:  ./check_scene_gate.sh --approve <name>")
    return 0


def _finding(name, ok, detail):
    from bridge.scene_gate import GeometryFinding
    return GeometryFinding(name, ok, detail)


def _recess_colours_visible(arr, scene_cfg, hue_tol=0.06, min_sat=0.06, min_pixels=25):
    """Which board recesses actually appear in the render, matched by HUE.

    Absolute RGB matching does not survive contact with a renderer: under RTX
    lighting and tone mapping the configured [0.20, 0.55, 0.45] arrives as a pale
    mint, tens of RGB units from its authored value, and every recess reported
    missing on a render where they were plainly visible. Hue is what survives an
    exposure change, which is the same reason the board alignment tool moved off
    colour thresholding onto phase correlation.
    """
    import colorsys

    import numpy as np

    a = np.clip(arr / 255.0, 0.0, 1.0)
    mx, mn = a.max(axis=2), a.min(axis=2)
    diff = mx - mn
    sat = np.where(mx > 0, diff / np.maximum(mx, 1e-6), 0.0)

    # Vectorised hue, matching colorsys' 0..1 convention.
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    hue = np.zeros_like(mx)
    safe = diff > 1e-6
    with np.errstate(invalid="ignore"):
        hr = np.where((mx == r) & safe, ((g - b) / np.where(safe, diff, 1)) % 6, np.nan)
        hg = np.where((mx == g) & safe, ((b - r) / np.where(safe, diff, 1)) + 2, np.nan)
        hb = np.where((mx == b) & safe, ((r - g) / np.where(safe, diff, 1)) + 4, np.nan)
    hue = np.nanmax(np.dstack([hr, hg, hb]), axis=2) / 6.0
    hue = np.nan_to_num(hue)

    found, missing = set(), set()
    for rec in scene_cfg.get("board", {}).get("recesses", []):
        cr, cg, cb = rec.get("color", [0.5, 0.5, 0.5])
        target_h, _, _ = colorsys.rgb_to_hsv(cr, cg, cb)
        dh = np.abs(hue - target_h)
        dh = np.minimum(dh, 1.0 - dh)  # hue is circular
        n = int(((dh < hue_tol) & (sat > min_sat)).sum())
        (found if n >= min_pixels else missing).add(rec["id"])
    return found, missing


if __name__ == "__main__":
    raise SystemExit(main())
