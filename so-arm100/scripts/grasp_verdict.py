"""Read a rollout manifest and say whether the arm actually grasped the piece.

Why this exists
---------------
The RUNBOOK's eval protocol is "counted by watching" because there is no
automatic success detector. That stays true for the *insertion* -- nothing in
the manifest distinguishes a piece seated in the pocket from one dropped beside
it -- but the *grasp* turns out to be readable directly off the gripper channel,
because a gripper closing onto a 13mm knob stops where the knob is:

    bench1 ok    grip settles 7.4      bench5 FAIL  grip settles 2.4
    bench2 ok    grip settles 7.4      (closed on nothing, twice)
    bench4 ok    grip settles 7.6

Clean separation, no overlap. Thresholds below sit in the gap. They come from
only four trials on 2026-08-21, so widen them if a later run lands in between
rather than trusting the boundary.

Transport is read the same way: every success swung the base to ~25 after the
close, and the failure never left the 48-55 band it grasped in.

    python3 scripts/grasp_verdict.py outputs/hardware-test/<tag>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HOLDING_MIN = 6.0      # gripper resting here or above after a close = piece in hand
EMPTY_MAX = 5.0        # at or below = closed on nothing
TRANSPORT_BASE = 35.0  # base swings below this to carry the piece to the board

# Where the three successes closed, as (centre, half-width). Used only to say
# whether a failed close was out of posture -- it is not a gate.
SUCCESS_SHOULDER = (-7.1, 2.0)
SUCCESS_ELBOW = (40.3, 2.0)


def load(out_dir: Path) -> list[dict]:
    manifest = out_dir / "manifest.jsonl"
    if not manifest.exists():
        raise SystemExit(f"no manifest at {manifest}")
    return [json.loads(line) for line in manifest.open() if line.strip()]


def find_close(rows: list[dict]) -> int | None:
    """First chunk whose requested gripper starts open and ends closed."""
    for r in rows:
        g = [s["gripper"] for s in r["requested"]]
        if g and g[0] > 10 and g[-1] < 5:
            return r["chunk"]
    return None


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    rows = load(Path(sys.argv[1]))
    if not rows:
        raise SystemExit("manifest is empty")

    close = find_close(rows)
    if close is None:
        print("  GRASP: never commanded -- the policy held the gripper open for the")
        print("         whole rollout. Check the wrist framing at the start pose;")
        print("         an out-of-distribution view makes it hover (RUNBOOK, 2026-08-21).")
        return 1

    after = rows[close + 1]["state"]["gripper"] if close + 1 < len(rows) else None
    if after is None:
        print(f"  GRASP: close commanded on chunk {close}, but the rollout ended there")
        print("         -- no observation after it, so the grasp is unverified.")
        return 1

    if after <= EMPTY_MAX:
        s = rows[close]["state"]
        sh, el = s["shoulder"], s["elbow"]
        print(f"  GRASP FAILED: closed on nothing (gripper {after:.1f}, holding reads "
              f"{HOLDING_MIN:.0f}+).")
        print(f"         Posture at the close: shoulder {sh:.1f}, elbow {el:.1f} "
              f"(successes: shoulder {SUCCESS_SHOULDER[0]:.0f}+-{SUCCESS_SHOULDER[1]:.0f}, "
              f"elbow {SUCCESS_ELBOW[0]:.0f}+-{SUCCESS_ELBOW[1]:.0f}).")
        # Only blame the posture when the posture is actually off. bench7 on
        # 2026-08-21 closed at shoulder -8.2, elbow 39.0 -- squarely normal --
        # with the piece correctly framed, and still caught nothing. Saying
        # "closed too high" there sent the diagnosis in the wrong direction.
        off_sh = abs(sh - SUCCESS_SHOULDER[0]) > SUCCESS_SHOULDER[1]
        off_el = abs(el - SUCCESS_ELBOW[0]) > SUCCESS_ELBOW[1]
        if off_sh or off_el:
            print("         That is outside the band the successes close in: the "
                  "gripper shut short of the peg.")
        else:
            print("         That is INSIDE the successes' band, so height does not "
                  "explain this one.")
            print("         Look at the close chunk's wrist.png -- an in-posture miss "
                  "means the piece moved,")
            print("         or the grasp is simply unreliable at this rate.")
        return 1
    if after < HOLDING_MIN:
        print(f"  GRASP UNCLEAR: gripper settled at {after:.1f}, between the empty "
              f"({EMPTY_MAX:.0f}) and holding ({HOLDING_MIN:.0f}) thresholds.")
        print("         Watch the video; then widen the thresholds in this file.")
        return 1

    transported = any(r["state"]["base"] < TRANSPORT_BASE for r in rows[close + 1:])
    print(f"  GRASP OK: gripper settled at {after:.1f} on the piece (chunk {close}).")
    if transported:
        print("  TRANSPORT OK: the base swung to the board afterwards.")
        print("  INSERTION: not machine-checkable -- confirm by eye or from "
              "the final overview.png.")
    else:
        print("  TRANSPORT FAILED: it grasped but never carried the piece to the board.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
