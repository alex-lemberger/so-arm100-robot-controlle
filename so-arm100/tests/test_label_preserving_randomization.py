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
PRESERVING_FIELDS = ("yaw_deg", "mass_scale", "friction_scale", "robot_joint_noise_deg", "camera_noise_std")


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


if __name__ == "__main__":
    results = {}
    for fn in (
        test_pose_axes_are_inert_by_default,
        test_opting_in_actually_varies_the_pose,
        test_gate_does_not_disturb_the_random_stream,
        test_provenance_records_the_choice,
        test_legacy_config_is_refused_not_silently_honoured,
        test_shipped_config_has_no_top_level_pose_keys,
    ):
        print(f"\n{fn.__name__}:")
        results[fn.__name__] = fn()
    failed = [k for k, v in results.items() if not v]
    print("\n" + ("ALL PASS" if not failed else f"FAILED: {failed}"))
    sys.exit(1 if failed else 0)
