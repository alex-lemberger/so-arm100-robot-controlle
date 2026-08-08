"""Health check for a single schemaVersion-2 app recording.

Run this on the first episode of a session before recording 50 more. It answers
the questions that have historically only surfaced at dataset-build time, when
the whole batch was already unusable:

  - did measured telemetry actually land, and at what rate?
  - did the arm actually MOVE? (two lerobot-record takes captured 1,499 frames
    of a motionless arm because the operator couldn't see the recording window)
  - do commanded and measured diverge dynamically under motion? (the spec's
    one remaining unverified claim -- a constant gap only proves gravity droop)
  - does the gripper open and close?
  - do the videos line up with the sample timeline?

Usage:
    python robot_learning/inspect_episode.py                 # newest episode
    python robot_learning/inspect_episode.py <episode-dir>
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_lerobot_dataset_v2 import (  # noqa: E402
    DEFAULT_CALIBRATION,
    SERVO_TO_MOTOR,
    load_calibration,
    normalize_ticks,
)

EPISODES_ROOT = Path("data/local/episodes")
OK, WARN, BAD = "  OK  ", " WARN ", " FAIL "


def check(label: str, status: str, detail: str = "") -> bool:
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    return status == OK


def video_info(path: Path) -> tuple[int, float] | None:
    try:
        import av
    except ImportError:
        return None
    try:
        container = av.open(str(path))
        stream = container.streams.video[0]
        count, last = 0, 0.0
        for frame in container.decode(stream):
            count += 1
            last = float(frame.pts * stream.time_base)
        container.close()
        return count, last
    except Exception:
        return None


def main() -> int:
    if len(sys.argv) > 1:
        episode_dir = Path(sys.argv[1])
    else:
        candidates = sorted(p for p in EPISODES_ROOT.glob("*") if (p / "metadata.json").is_file())
        if not candidates:
            print(f"No episodes found under {EPISODES_ROOT}")
            return 1
        episode_dir = candidates[-1]

    print(f"\nInspecting: {episode_dir}\n" + "=" * 72)
    metadata = json.loads((episode_dir / "metadata.json").read_text())

    failures = 0
    version = metadata.get("schemaVersion")
    if version != 2:
        check("schemaVersion is 2", BAD, f"got {version!r} — this recorder build is not the v2 one")
        return 1
    check("schemaVersion is 2", OK)

    ts = metadata["timeseries"]
    samples = ts["samples"]
    duration_s = metadata["durationMs"] / 1000.0
    total, measured_n = len(samples), ts["measuredSampleCount"]

    print(f"\nDuration {duration_s:.1f}s · {total} samples · {measured_n} with telemetry\n")

    # --- sample rate -------------------------------------------------------
    hz = ts["achievedSampleRateHz"]
    target = ts["targetSampleRateHz"]
    if hz >= target * 0.9:
        check(f"sample rate {hz} Hz", OK, f"target {target} Hz")
    elif hz >= 15:
        check(f"sample rate {hz} Hz", WARN,
              f"below the {target} Hz target but usable; build at fps={int(hz)}")
    else:
        failures += 1
        check(f"sample rate {hz} Hz", BAD, "too slow — the serial reads need batching into a sync-read")

    # --- telemetry coverage ------------------------------------------------
    if measured_n == 0:
        failures += 1
        check("measured telemetry present", BAD, "NONE — episode is unusable for training")
        return 1
    coverage = measured_n / total
    if coverage >= 0.99:
        check("measured telemetry coverage", OK, f"{coverage:.1%}")
    elif coverage >= 0.9:
        check("measured telemetry coverage", WARN, f"{coverage:.1%} — {total - measured_n} reads timed out")
    else:
        failures += 1
        check("measured telemetry coverage", BAD, f"{coverage:.1%} — bus is dropping too many reads")

    # --- did the arm actually move? ---------------------------------------
    meas = [(s["tMs"] / 1000, {int(k): v for k, v in s["measured"]["ticks"].items()})
            for s in samples if s.get("measured")]
    cmd = [(s["tMs"] / 1000, {int(k): v for k, v in s["commanded"]["ticks"].items()})
           for s in samples if s.get("commanded", {}).get("ticks")]

    if not cmd:
        failures += 1
        check("commanded ticks present", BAD, "none — calibration missing while recording?")
        return 1

    meas_arr = np.array([[t[sid] for sid, _ in SERVO_TO_MOTOR] for _, t in meas], dtype=float)
    cmd_arr = np.array([[t[sid] for sid, _ in SERVO_TO_MOTOR] for _, t in cmd], dtype=float)

    travel = meas_arr.max(axis=0) - meas_arr.min(axis=0)
    print()
    if travel.max() < 20:
        failures += 1
        check("arm moved during the take", BAD,
              f"max travel {travel.max():.0f} ticks — this looks like a motionless recording")
    else:
        check("arm moved during the take", OK, f"max travel {travel.max():.0f} ticks")

    # --- dynamic divergence: the spec's open question ----------------------
    # Pair by timestamp, not by index: a dropped telemetry read shifts the two
    # lists relative to each other, which would compare samples from different
    # moments and inflate the gap into a false pass.
    cmd_by_t = {round(t, 4): row for t, row in zip((t for t, _ in cmd), cmd_arr)}
    paired = [(cmd_by_t[round(t, 4)], row)
              for (t, _), row in zip(meas, meas_arr) if round(t, 4) in cmd_by_t]
    if not paired:
        check("commanded/measured diverge dynamically", WARN, "no timestamp-aligned pairs")
        gap_std = np.zeros(6)
    else:
        gap = np.array([c - m for c, m in paired])
        gap_std = gap.std(axis=0)
    if paired and gap_std.max() > 3:
        check("commanded/measured diverge dynamically", OK,
              f"gap std up to {gap_std.max():.1f} ticks over {len(paired)} aligned pairs")
    elif paired:
        check("commanded/measured diverge dynamically", WARN,
              f"gap std only {gap_std.max():.1f} ticks — mostly constant droop; move faster to confirm")

    # --- gripper -----------------------------------------------------------
    grip_travel = travel[5]
    if grip_travel < 20:
        check("gripper actuated", WARN, f"travel {grip_travel:.0f} ticks — did the grasp happen?")
    else:
        check("gripper actuated", OK, f"travel {grip_travel:.0f} ticks")

    # --- tick sanity -------------------------------------------------------
    if meas_arr.min() < 0 or meas_arr.max() > 4095:
        failures += 1
        check("ticks within [0, 4095]", BAD, f"range {meas_arr.min():.0f}..{meas_arr.max():.0f}")
    else:
        check("ticks within [0, 4095]", OK)

    # --- videos ------------------------------------------------------------
    print()
    for role in ("overview", "wrist"):
        path = episode_dir / metadata["observations"][role]["file"]
        if not path.is_file():
            failures += 1
            check(f"{role} video", BAD, "missing")
            continue
        info = video_info(path)
        if info is None:
            check(f"{role} video", WARN, f"{path.stat().st_size / 1e6:.1f} MB (could not decode here)")
            continue
        count, last_t = info
        drift = abs(last_t - duration_s)
        detail = f"{count} frames, {last_t:.1f}s, {path.stat().st_size / 1e6:.1f} MB"
        if drift > 1.0:
            check(f"{role} video", WARN, detail + f" — {drift:.1f}s off the sample timeline")
        else:
            check(f"{role} video", OK, detail)

    # --- what the dataset will look like -----------------------------------
    try:
        calibration = load_calibration(Path(DEFAULT_CALIBRATION))
        state_first = normalize_ticks(meas[0][1], calibration)
        state_last = normalize_ticks(meas[-1][1], calibration)
        print("\nIn LeRobot units (what training actually sees):")
        for i, (_, motor) in enumerate(SERVO_TO_MOTOR):
            unit = "%" if motor == "gripper" else "°"
            print(f"  {motor:<14} {state_first[i]:>8.2f}{unit} -> {state_last[i]:>8.2f}{unit}")
    except Exception as exc:
        check("tick -> LeRobot units", WARN, str(exc))

    print("\n" + "=" * 72)
    if failures:
        print(f"{failures} blocking problem(s). Do NOT record 50 episodes yet.")
        return 1
    print("Looks good. Safe to record the full session.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
