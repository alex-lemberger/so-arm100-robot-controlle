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


def recess_center(bgr: np.ndarray) -> tuple[float, float, int]:
    """Centroid of the green board features, ignoring the loose piece on the left."""
    b, g, r = (bgr[:, :, i].astype(int) for i in range(3))
    mask = (g > 90) & (g - r > 35) & (g - b > 15)
    mask[:, :430] = False
    mask[:150, :] = False
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return float("nan"), float("nan"), 0
    return xs.mean(), ys.mean(), len(xs)


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

    rx, ry, rn = recess_center(ref)
    lx, ly, ln = recess_center(live)
    dx, dy = lx - rx, ly - ry
    dist = (dx**2 + dy**2) ** 0.5

    # ~200mm board spanning ~340px in this view.
    mm = dist * 200.0 / 340.0

    print(f"reference green centroid: ({rx:7.1f}, {ry:7.1f})  [{rn} px]")
    print(f"live      green centroid: ({lx:7.1f}, {ly:7.1f})  [{ln} px]")
    print(f"OFFSET  dx={dx:+.1f}px  dy={dy:+.1f}px  |d|={dist:.1f}px  (~{mm:.0f} mm)")
    if dist < 5:
        print("ALIGNED -- good enough to run the eval.")
    else:
        print(f"MOVE THE BOARD {'left' if dx > 0 else 'right'} "
              f"and {'up' if dy > 0 else 'down'}, then re-run.")
        print("Check the overlay for rotation too -- if the doubling grows toward")
        print("one edge of the board, it is rotated, not just translated.")

    cv2.imwrite(args.out, cv2.addWeighted(ref, 0.5, live, 0.5, 0))
    print(f"overlay written to {args.out}")


if __name__ == "__main__":
    main()
