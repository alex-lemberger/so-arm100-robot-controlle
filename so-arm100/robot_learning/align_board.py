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


def peg_centroid(bgr):
    """The loose peg on the paper: saturated green-cyan, left of the board region.

    Grasping does not involve the board at all, so board alignment says nothing
    about whether the peg is where the demos had it. Measured 2026-08-14: the
    demos cluster the peg tightly (x 371-396, y 556-583) and it was being placed
    ~22mm outside that, while grasp success sat at 2/7 and 4/9.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s_, v = hsv[:, :, 0].astype(int), hsv[:, :, 1].astype(int), hsv[:, :, 2].astype(int)
    mask = ((h > 70) & (h < 100) & (s_ > 60) & (v > 50)).astype(np.uint8)
    mask[:, 430:] = 0    # exclude the board's own recesses
    mask[:380, :] = 0    # exclude the arm
    n, _lab, stats, cent = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[i, cv2.CC_STAT_AREA] < 200:
        return None
    return cent[i]


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
    live = None
    for _ in range(10):  # let auto-exposure settle
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
    if dist < 5:
        print("ALIGNED -- good enough to run the eval.")
    else:
        print(f"MOVE THE BOARD {abs(dx):.0f}px {'left' if dx > 0 else 'right'} "
              f"and {abs(dy):.0f}px {'up' if dy > 0 else 'down'} "
              f"(~{abs(dx)*MM_PER_PX:.0f}mm / ~{abs(dy)*MM_PER_PX:.0f}mm), then re-run.")
        print("  'right'/'down' are as seen in the OVERVIEW CAMERA IMAGE, not from")
        print("  where you stand: image-right is the towel/cable side of the paper,")
        print("  image-down is toward the paper's near edge.")

    ref_peg, live_peg = peg_centroid(ref), peg_centroid(live)
    if ref_peg is None or live_peg is None:
        print("\nPEG: could not locate it in one of the frames "
              f"(reference={'ok' if ref_peg is not None else 'MISSING'}, "
              f"live={'ok' if live_peg is not None else 'MISSING'})")
    else:
        pdx, pdy = live_peg[0] - ref_peg[0], live_peg[1] - ref_peg[1]
        pdist = (pdx**2 + pdy**2) ** 0.5
        print(f"\nPEG  dx={pdx:+.1f}px dy={pdy:+.1f}px  |d|={pdist:.1f}px (~{pdist*MM_PER_PX:.0f} mm)")
        if pdist < 12:
            print("  peg is where the demos put it.")
        else:
            print(f"  MOVE THE PEG {abs(pdx)*MM_PER_PX:.0f}mm "
                  f"{'left' if pdx > 0 else 'right'} and {abs(pdy)*MM_PER_PX:.0f}mm "
                  f"{'up' if pdy > 0 else 'down'} (image directions, as above).")
            print("  Grasping does not involve the board, so this is the one that")
            print("  matters for the grasp failures.")

    cv2.imwrite(args.out, cv2.addWeighted(ref, 0.5, live, 0.5, 0))
    print(f"overlay written to {args.out}")


if __name__ == "__main__":
    main()
