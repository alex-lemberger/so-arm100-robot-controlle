"""The label-breaking randomization gate (2026-08-15).

scripts/generate_synthetic.py copies the parent episode's actions verbatim, so
randomizing the object's or board's POSE produces frames whose labels point at the
target's old location. That trains the policy to ignore the target's position --
the exact failure being fought on hardware. These checks pin down that the pose
axes are inert by default, that turning them on is an explicit act, and that the
gate did not disturb the random stream every already-generated seed depends on.

Pure numpy + yaml, no Isaac. Run:

    docker run --rm -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" lerobot-train:latest \
        python3 tests/test_label_preserving_randomization.py
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from augmentation.randomization import sample_variation  # noqa: E402

CFG = yaml.safe_load((ROOT / "configs" / "simulation.yaml").read_text())
RCFG = CFG["randomization"]
POSE_FIELDS = ("object_offset_x", "object_offset_y", "board_offset_x", "board_offset_y", "board_yaw_deg")
PRESERVING_FIELDS = ("yaw_deg", "mass_scale", "friction_scale", "robot_joint_noise_deg",
                     "camera_noise_std", "light_intensity_scale", "distant_light_yaw_deg")


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  -- ' + detail if detail and not cond else ''}")
    return cond


def test_pose_axes_are_inert_by_default():
    """The shipped config must not produce a single non-zero pose offset unasked."""
    ok = True
    for f in POSE_FIELDS:
        leaks = [(s, getattr(sample_variation(RCFG, seed=s), f)) for s in range(200)]
        leaks = [(s, v) for s, v in leaks if v != 0.0]
        ok &= check(f"{f} stays 0 across 200 seeds", not leaks, f"non-zero at {leaks[:3]}")
    return ok


def test_opting_in_actually_varies_the_pose():
    """The gate must not be a permanent off switch -- the ranges are still live."""
    ok = True
    xs = [sample_variation(RCFG, seed=s, allow_label_breaking=True) for s in range(50)]
    for f in POSE_FIELDS:
        vals = [getattr(v, f) for v in xs]
        ok &= check(f"{f} varies when opted in", len(set(vals)) > 1 and any(v != 0.0 for v in vals))
    return ok


def test_gate_does_not_disturb_the_random_stream():
    """Rule 10: every label-preserving value for a seed must be identical either way,
    because the pose draws still happen and are only discarded afterwards. If this
    fails, every seed recorded in data/synthetic/ reproduces different episodes."""
    ok = True
    for seed in (0, 1, 42, 12345, 99999):
        off = sample_variation(RCFG, seed=seed)
        on = sample_variation(RCFG, seed=seed, allow_label_breaking=True)
        same = all(getattr(off, f) == getattr(on, f) for f in PRESERVING_FIELDS)
        ok &= check(f"seed {seed}: label-preserving draws unchanged by the gate", same)
    return ok


def test_provenance_records_the_choice():
    """A generated dataset has to be auditable from its own episode records."""
    off = sample_variation(RCFG, seed=7)
    on = sample_variation(RCFG, seed=7, allow_label_breaking=True)
    ok = check("default records label_breaking_applied=False", off.label_breaking_applied is False)
    ok &= check("opt-in records label_breaking_applied=True", on.label_breaking_applied is True)
    ok &= check("the flag survives as_dict()", on.as_dict().get("label_breaking_applied") is True)
    return ok


def test_legacy_config_is_refused_not_silently_honoured():
    """A pre-split config puts the pose keys at the top level. Honouring it would
    generate harmful data silently, so it must raise instead."""
    ok = True
    for key in ("object_position", "board_position", "board_rotation_deg"):
        legacy = {**RCFG, key: RCFG["label_breaking"][key]}
        try:
            sample_variation(legacy, seed=0)
            ok &= check(f"top-level {key} is refused", False, "no error raised")
        except ValueError as exc:
            ok &= check(f"top-level {key} is refused", key in str(exc), str(exc))
    return ok


def test_shipped_config_has_no_top_level_pose_keys():
    ok = True
    for key in ("object_position", "board_position", "board_rotation_deg"):
        ok &= check(f"simulation.yaml keeps {key} under label_breaking:",
                    key not in RCFG and key in RCFG["label_breaking"])
    return ok


def test_lighting_varies_without_any_opt_in():
    """Lighting is label-preserving, so it must be live in the shipped config with no
    flag. If this fails the synthetic data has no visual variation at all -- which is
    what it had between the pose gate landing and the lighting axis arriving."""
    vs = [sample_variation(RCFG, seed=s) for s in range(200)]
    scales = [v.light_intensity_scale for v in vs]
    yaws = [v.distant_light_yaw_deg for v in vs]
    lo, hi = RCFG["light_intensity_scale"]["min"], RCFG["light_intensity_scale"]["max"]
    ylo, yhi = RCFG["distant_light_yaw_deg"]

    ok = check("intensity scale varies by default", len(set(scales)) > 100)
    ok &= check("intensity scale within configured range", lo <= min(scales) and max(scales) <= hi,
                f"[{min(scales):.3f}, {max(scales):.3f}] vs [{lo}, {hi}]")
    ok &= check("light yaw varies by default", len(set(yaws)) > 100)
    ok &= check("light yaw within configured range", ylo <= min(yaws) and max(yaws) <= yhi,
                f"[{min(yaws):.2f}, {max(yaws):.2f}] vs [{ylo}, {yhi}]")
    # The whole justification: rollout_grasp_v1_r1 ran at ~0.80 of the demos'
    # brightness (V 151-164 vs 180-188). That has to sit INSIDE the range, not at
    # its edge, or the axis does not cover the shift it was added for.
    ok &= check("range covers the measured 0.80 workspace darkening with margin", lo < 0.80,
                f"min {lo} does not get below the measured 0.80")
    return ok


def test_lighting_draws_appended_last():
    """Rule 10 again: the lighting draws must come after every pre-existing draw, so
    a seed still reproduces the exact pre-lighting variation of data/synthetic/."""
    stripped = {k: v for k, v in RCFG.items() if k not in ("light_intensity_scale", "distant_light_yaw_deg")}
    ok = True
    for seed in (0, 1, 42, 12345):
        with_light = sample_variation(RCFG, seed=seed, allow_label_breaking=True)
        without = sample_variation(stripped, seed=seed, allow_label_breaking=True)
        same = all(
            getattr(with_light, f) == getattr(without, f)
            for f in ("object_offset_x", "object_offset_y", "yaw_deg", "mass_scale", "friction_scale",
                      "robot_joint_noise_deg", "board_offset_x", "board_offset_y", "board_yaw_deg")
        )
        ok &= check(f"seed {seed}: pre-lighting draws unchanged by adding lighting", same)
        ok &= check(f"seed {seed}: absent lighting config -> neutral lighting",
                    without.light_intensity_scale == 1.0 and without.distant_light_yaw_deg == 0.0)
    return ok


def test_pre_lighting_records_reconstruct_neutral():
    """scripts/export_lerobot_dataset.py rebuilds Variation(**record["randomization"]).
    Records written before the lighting axis existed have no light fields; they must
    reconstruct at baseline lighting rather than raising or picking up a random value."""
    from dataclasses import fields

    from augmentation.randomization import Variation

    legacy = {f.name: getattr(sample_variation(RCFG, seed=3), f.name) for f in fields(Variation)}
    for k in ("light_intensity_scale", "distant_light_yaw_deg", "label_breaking_applied"):
        legacy.pop(k)
    try:
        v = Variation(**legacy)
    except TypeError as exc:
        return check("legacy record reconstructs", False, str(exc))
    ok = check("legacy record reconstructs", True)
    ok &= check("legacy record lights are neutral",
                v.light_intensity_scale == 1.0 and v.distant_light_yaw_deg == 0.0)
    return ok


if __name__ == "__main__":
    results = {}
    for fn in (
        test_pose_axes_are_inert_by_default,
        test_opting_in_actually_varies_the_pose,
        test_gate_does_not_disturb_the_random_stream,
        test_provenance_records_the_choice,
        test_legacy_config_is_refused_not_silently_honoured,
        test_shipped_config_has_no_top_level_pose_keys,
        test_lighting_varies_without_any_opt_in,
        test_lighting_draws_appended_last,
        test_pre_lighting_records_reconstruct_neutral,
    ):
        print(f"\n{fn.__name__}:")
        results[fn.__name__] = fn()
    failed = [k for k, v in results.items() if not v]
    print("\n" + ("ALL PASS" if not failed else f"FAILED: {failed}"))
    sys.exit(1 if failed else 0)
