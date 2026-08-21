"""Read a rollout manifest and say whether the arm actually grasped the piece.

Why this exists
---------------
The RUNBOOK's eval protocol is "counted by watching" because there is no
automatic success detector. That stays true for the *insertion* -- nothing in
the manifest distinguishes a piece seated in the pocket from one dropped beside
it -- but the *grasp* turns out to be readable off the OBSERVED gripper channel,
because a gripper closing onto a 13mm knob stops where the knob is and stays:

    bench1  ... 14.4 14.2 13.8  7.4  7.4  7.4  7.4 11.6   grasped, held 4 chunks
    fixed02 ... 13.6 14.1 14.0  7.4  7.4  7.4 11.4        grasped, held 3 chunks
    bench5  ... 14.2 14.1 13.8  2.4  4.7 14.0             closed on nothing
    bench7  ... 14.6 14.0  2.4  8.4 13.0  8.2 11.3        missed, then flailed
    bench3  ... 14.4 14.4 14.1 14.1 14.2 14.2 14.0        never closed at all

Read the *observed* channel, never the requested one: requested says what the
policy wanted at replan time, including closes it abandons a moment later. And
require persistence -- bench7 clipped the holding band for a single chunk (8.4)
without ever holding anything, so one reading in range proves nothing.

Transport is read the same way: every success swung the base to ~25 afterwards,
and no failure ever left the 45-56 band it tried to grasp in.

    python3 scripts/grasp_verdict.py outputs/hardware-test/<tag>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HOLDING_MIN = 6.0      # gripper holding the knob rests in
HOLDING_MAX = 10.0     # this band, for more than one chunk
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


def analyse(rows: list[dict]) -> tuple[str, int | None]:
    """Classify the rollout from the OBSERVED gripper, not the requested one.

    Two earlier versions of this got it wrong by reading predictions. Requested
    values say what the policy wanted at replan time, including closes it then
    abandons; the observed channel says what the hardware did. The tell is
    persistence -- a gripper holding the 13mm knob sits at 7.4-7.6 for several
    consecutive chunks, where a miss either bottoms out near 2.4 or clips the
    band for one chunk and springs back open (bench6 10.1 then 12.0, bench7 8.4
    then 13.0, both on 2026-08-21).

    Returns (verdict, chunk) where verdict is one of grasped / empty / never.
    """
    grip = [r["state"]["gripper"] for r in rows]
    opened = None
    for i, g in enumerate(grip):
        if g > 10:
            opened = i
            break
    if opened is None:
        return "never", None

    first_close = None
    for i in range(opened + 1, len(grip)):
        if grip[i] > 10:
            continue
        if first_close is None:
            first_close = i
        # A real grasp holds. One chunk in the band proves nothing.
        if HOLDING_MIN <= grip[i] <= HOLDING_MAX:
            nxt = grip[i + 1] if i + 1 < len(grip) else None
            if nxt is not None and HOLDING_MIN <= nxt <= HOLDING_MAX:
                return "grasped", i
    if first_close is None:
        return "never", None
    return "empty", first_close


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    rows = load(Path(sys.argv[1]))
    if not rows:
        raise SystemExit("manifest is empty")

    verdict, chunk = analyse(rows)

    if verdict == "never":
        print("  GRASP: never closed -- the gripper stayed open for the whole")
        print("         rollout. Check the wrist framing at the start pose; an")
        print("         out-of-distribution view makes it hover (RUNBOOK, 2026-08-21).")
        return 1

    s = rows[chunk]["state"]
    sh, el = s["shoulder"], s["elbow"]

    if verdict == "empty":
        print(f"  GRASP FAILED: closed on nothing (gripper {rows[chunk]['state']['gripper']:.1f} "
              f"at chunk {chunk}; holding reads {HOLDING_MIN:.0f}-{HOLDING_MAX:.0f} and stays there).")
        print(f"         Posture at the close: shoulder {sh:.1f}, elbow {el:.1f} "
              f"(successes: shoulder {SUCCESS_SHOULDER[0]:.0f}+-{SUCCESS_SHOULDER[1]:.0f}, "
              f"elbow {SUCCESS_ELBOW[0]:.0f}+-{SUCCESS_ELBOW[1]:.0f}).")
        # Only blame the posture when the posture is actually off. bench7 on
        # 2026-08-21 closed at shoulder -8.2, elbow 39.0 -- squarely normal --
        # with the piece correctly framed, and still caught nothing. Saying
        # "closed too high" there sent the diagnosis in the wrong direction.
        off = (abs(sh - SUCCESS_SHOULDER[0]) > SUCCESS_SHOULDER[1]
               or abs(el - SUCCESS_ELBOW[0]) > SUCCESS_ELBOW[1])
        if off:
            print("         That is outside the band the successes close in: the "
                  "gripper shut short of the peg.")
        else:
            print("         That is INSIDE the successes' band, so height does not "
                  "explain this one.")
            print("         Look at that chunk's wrist.png -- an in-posture miss means "
                  "the piece moved,")
            print("         or the grasp is simply unreliable at this rate.")
        return 1

    transported = any(r["state"]["base"] < TRANSPORT_BASE for r in rows[chunk:])
    print(f"  GRASP OK: gripper held at {rows[chunk]['state']['gripper']:.1f} on the "
          f"piece from chunk {chunk}.")
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
