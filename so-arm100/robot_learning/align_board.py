"""Overlay the live overview camera on a reference frame from the training demos.

The board drifted ~18mm (plus a few degrees) between when circle_insert_50ep was
recorded and the 2026-08-14 R0 eval, which is the leading explanation for
policies that grasp and transport correctly but never seat the piece. Insertion
needs millimetre precision at a board pose the policy has largely memorised, so
the board has to go back where the demos had it.

Run it, look at the PNG, nudge the board, run it again. Aim for < ~5 px.

    ./check_alignment.sh
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE = REPO_ROOT / "docs" / "reference" / "board_reference_demo.png"
MM_PER_PX = 107.0 / 172.4  # see the note in main()


# Where the demos put the loose peg, in the reference frame.
PEG_REF_XY = (371, 574)
PEG_RADIUS = 46

# What the DEMOS actually did, measured at the first frame of all 81 episodes of
# circle_grasp_v1 by scripts/measure_setup_distribution.py (2026-08-16). Offsets are
# from this file's reference frame, in pixels.
#
# These replace a pair of fixed thresholds (<5px board, <12px peg) that were guesses,
# and the peg one was wrong by a factor of three in the WRONG DIRECTION -- it demanded
# the peg be placed more precisely than the demos ever placed it, and duly reported a
# correct setup as needing a 23mm correction.
#
# The board and the peg are not the same kind of quantity, and that is the finding:
#
#   board:  dx +1.0 +/- 1.4, dy +0.2 +/- 0.3, max |d| 4.1px (2.5mm) over 46 episodes
#           -- held still to within a couple of millimetres, all session.
#   peg:    dx +21.1 +/- 24.0, dy +1.2 +/- 16.6, median |d| 34px (21mm) over 36
#           -- scattered. The policy saw the peg all over the paper and cannot be
#           expecting it in one spot.
#
# So the board is worth aligning precisely and the peg is worth only a sanity check.
# (Sample sizes are below 81 because frames where the arm occludes the peg, or the
# board's correlation is weak, are dropped rather than guessed at.)
DEMO_BOARD = {"dx": 1.0, "dy": 0.2, "max_dist": 4.1}
DEMO_PEG = {"dx": 21.1, "dy": 1.2, "sd_x": 24.0, "sd_y": 16.6}


def _gradient(bgr):
    """Normalised gradient magnitude -- an illumination-invariant view of a frame."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    return mag / (mag.max() + 1e-6)


def peg_offset(ref_bgr, live_bgr):
    """Where the loose peg is now, relative to where the demos had it.

    Matched on gradient, not colour. Colour thresholding is what this function used
    until 2026-08-16 and it fails exactly the way `board_shift`'s docstring already
    describes for the board: under warm evening light the peg's hue slides out of the
    70-100 window and the detector returns MISSING with no other symptom. Measured
    that evening: the paper's own median saturation went 22 -> 63 and 94% of its red
    channel was clipped at 255, so there was no absolute colour threshold left to
    thresh on. board_shift was moved to phase correlation for this reason; the peg
    check was left behind on the approach that had already been shown not to work.

    Grasping does not involve the board at all, so this is the check that bears on
    the grasp failures -- the one it is least affordable to have silently unavailable.

    Returns (dx, dy, score); score is normalised cross-correlation, ~0.8 on a good
    match. Below ~0.5, treat the position as unknown rather than believing it.
    """
    cx, cy = PEG_REF_XY
    r = PEG_RADIUS
    template = _gradient(ref_bgr)[cy - r:cy + r, cx - r:cx + r]
    # Search the paper left of the board, below the arm -- the peg's whole plausible
    # range, and nowhere the board's own recesses could match instead.
    x0, x1, y0, y1 = 150, 470, 380, 720
    result = cv2.matchTemplate(_gradient(live_bgr)[y0:y1, x0:x1], template,
                               cv2.TM_CCOEFF_NORMED)
    _minv, score, _minl, loc = cv2.minMaxLoc(result)
    return loc[0] + x0 + r - cx, loc[1] + y0 + r - cy, score


# A patch of bare paper, clear of the board, the arm and the clutter on the right.
# The workspace's own white reference.
PAPER_PATCH = (slice(560, 700), slice(600, 900))


def illumination(bgr):
    """(median saturation, %% of the red channel clipped) on the bare paper.

    The paper is white, so on a neutral-lit frame its saturation is near zero and
    nothing clips. Both numbers moving means the room's colour temperature has moved,
    which is a distribution shift the policy never saw -- and, past a point, destroyed
    information rather than shifted information.

    Added 2026-08-16, when a session was nearly evaluated under warm evening light:
    the paper's median saturation had gone 22 -> 63 and 94%% of its red channel was
    clipped at 255. That is not the ~15%% brightness difference already on record; it
    is a different white point with a blown channel, and it would have made the run
    incomparable to the baseline it was meant to extend.
    """
    patch = bgr[PAPER_PATCH]
    sat = float(np.median(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[:, :, 1]))
    clipped = float((patch[:, :, 2] >= 254).mean() * 100)
    return sat, clipped


def board_shift(ref_bgr: np.ndarray, live_bgr: np.ndarray) -> tuple[float, float, float]:
    """Translation of the board between two frames, via phase correlation.

    Colour thresholding was the first approach and it is not usable across
    sessions: warmer evening light dropped the green pixel count from 5764 to
    2841 and the centroid moved with it, giving a reading that drifted 15px
    between two consecutive captures of a stationary board. Phase correlation
    on gradient magnitude keys on edges instead of absolute colour, so it
    survives an exposure change.
    """
    # The board only. Excludes the arm, the loose piece, and the background.
    x0, x1, y0, y1 = 420, 830, 150, 540

    def prep(bgr):
        g = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        mag /= (mag.max() + 1e-6)
        return mag * cv2.createHanningWindow((x1 - x0, y1 - y0), cv2.CV_32F)

    (dx, dy), response = cv2.phaseCorrelate(prep(ref_bgr), prep(live_bgr))
    return dx, dy, response


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", default="/dev/video0", help="overview camera")
    ap.add_argument("--out", default="board_alignment.png")
    ap.add_argument("--reference", default=str(REFERENCE))
    args = ap.parse_args()

    ref = cv2.imread(args.reference)
    if ref is None:
        raise SystemExit(f"reference frame not found: {args.reference}")

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    # Auto-exposure AND auto-white-balance both have to settle, and from a cold open
    # the white balance is far slower than the exposure. MEASURED 2026-08-16: the
    # first capture after plugging through read the bare paper at saturation 63 with
    # 94% of its red channel clipped -- a warm cast strong enough that the peg's hue
    # left the detector's window entirely -- and successive captures walked 63 -> 42
    # -> 29 -> 21 against the demos' 22. Ten frames read "the room's lighting is
    # wrong"; sixty read "it matches". The placement numbers were stable throughout,
    # so this only ever corrupted the colour judgements -- which is worse, because
    # they are the ones that look like a finding about the room.
    live = None
    for _ in range(60):
        ok, frame = cap.read()
        if ok:
            live = frame
    cap.release()
    if live is None:
        raise SystemExit(f"could not read from {args.camera}")

    if live.shape != ref.shape:
        live = cv2.resize(live, (ref.shape[1], ref.shape[0]))

    dx, dy, response = board_shift(ref, live)
    dist = (dx**2 + dy**2) ** 0.5

    # Calibrated against known geometry rather than guessed: in the reference
    # frame the circle recess sits at (515.6, 417.4) and the pentagon at
    # (555.8, 249.8), 172.4px apart, and docs/reference/toy.png puts those
    # centres 107mm apart. The previous constant came from an eyeballed "200mm
    # board over ~340px" before the board was measured at 174mm.
    mm = dist * MM_PER_PX

    print(f"board shift (live vs reference):  dx={dx:+.1f}px  dy={dy:+.1f}px")
    print(f"  |d|={dist:.1f}px  (~{mm:.0f} mm)   correlation={response:.3f}")
    if response < 0.10:
        print("WARNING: weak correlation -- is the arm parked over the board,")
        print("or the board out of the 420-830 x 150-540 crop? Check the overlay.")
    # Against the demos' own spread, not a round number: they held the board to
    # 4.1px worst-case, so anything inside that is inside the training distribution.
    if dist < DEMO_BOARD["max_dist"]:
        print("ALIGNED -- inside the spread the demos themselves had.")
    else:
        print(f"MOVE THE BOARD {abs(dx):.0f}px {'left' if dx > 0 else 'right'} "
              f"and {abs(dy):.0f}px {'up' if dy > 0 else 'down'} "
              f"(~{abs(dx)*MM_PER_PX:.0f}mm / ~{abs(dy)*MM_PER_PX:.0f}mm), then re-run.")
        print("  'right'/'down' are as seen in the OVERVIEW CAMERA IMAGE, not from")
        print("  where you stand: image-right is the towel/cable side of the paper,")
        print("  image-down is toward the paper's near edge.")

    ref_sat, ref_clip = illumination(ref)
    live_sat, live_clip = illumination(live)
    print(f"\nLIGHT  bare paper: saturation {live_sat:.0f} (demos {ref_sat:.0f}), "
          f"red channel clipped {live_clip:.0f}% (demos {ref_clip:.0f}%)")
    if live_clip > 20 or live_sat > ref_sat + 20:
        print("  LIGHTING IS OFF -- the room is a different colour temperature from the")
        print("  demos', and a clipped channel is information destroyed, not shifted.")
        print("  An eval run under this light is not comparable to one under theirs.")
        print("  Fix the light before running, not the numbers afterwards.")
    else:
        print("  close enough to the demos' lighting.")

    pdx, pdy, pscore = peg_offset(ref, live)
    pdist = (pdx**2 + pdy**2) ** 0.5
    print(f"\nPEG  dx={pdx:+.1f}px dy={pdy:+.1f}px  |d|={pdist:.1f}px "
          f"(~{pdist*MM_PER_PX:.0f} mm)  match={pscore:.3f}")
    if pscore < 0.5:
        print("  WEAK MATCH -- the peg was not found. Do not trust the offset above;")
        print("  check the overlay and that the peg is on the paper at all.")
    else:
        # How unusual is this placement FOR THE DEMOS -- not how far it is from one
        # frame. The demos scattered the peg, so distance-from-reference says nothing.
        zx = abs(pdx - DEMO_PEG["dx"]) / DEMO_PEG["sd_x"]
        zy = abs(pdy - DEMO_PEG["dy"]) / DEMO_PEG["sd_y"]
        print(f"  vs the demos' own placements: {zx:.1f} sd in x, {zy:.1f} sd in y "
              f"(they scattered it: dx {DEMO_PEG['dx']:+.0f}+/-{DEMO_PEG['sd_x']:.0f}px, "
              f"dy {DEMO_PEG['dy']:+.0f}+/-{DEMO_PEG['sd_y']:.0f}px)")
        if max(zx, zy) < 2.0:
            print("  peg is inside the spread the demos used. Leave it alone.")
        else:
            print("  peg is OUTSIDE the demos' spread -- move it toward the middle of")
            print("  their range. Grasping never involves the board, so the peg is the")
            print("  placement that bears on the grasp failures.")

    cv2.imwrite(args.out, cv2.addWeighted(ref, 0.5, live, 0.5, 0))
    print(f"overlay written to {args.out}")


if __name__ == "__main__":
    main()
