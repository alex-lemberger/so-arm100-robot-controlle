"""Success as a function of WHERE THE OBJECT WAS -- the measurement this project is
actually about.

A single success rate answers "did it work on the setup we staged". It cannot
distinguish a policy that sees the peg and adapts from one that replays a trajectory
that happens to end where the peg usually is. Those are the same number and opposite
outcomes, and the second one is what this project exists not to build.

So: label every episode with the peg's starting position, and report the outcome
against it. Placement stops being a nuisance to be nulled out before a run and
becomes the independent variable.

Outcomes are read off the video AND the gripper channel, not eye-scored:
  transport  -- the peg left the table region WHILE THE GRIPPER WAS CLOSED, i.e. it
                was picked up and carried.
  pushed-out -- the peg left the region with the gripper open: shoved, not carried.
  disturbed  -- the peg moved more than DISTURB_MM but stayed in the region.
  untouched  -- the arm never meaningfully moved it.

The gripper condition is not a detail. Without it, "the peg is no longer where it
was" counts a shove as a carry -- and on 2026-08-16 that reported 2 of 3 probe
episodes as transports in a run where a human watching said it never grasped once.
A metric that disagrees with the person watching the robot is wrong by default.

    ./analyse_placement.sh rollout_grasp_v1_r1 rollout_grasp_v1_r2
    ./analyse_placement.sh --demos circle_grasp_v1
"""
import argparse
import sys
from pathlib import Path

import av
import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MM_PER_PX = 107.0 / 172.4
STRIDE = 10           # sample every Nth frame; the peg does not move fast
DISTURB_MM = 15.0
GONE_SAMPLES = 5      # consecutive missing samples that count as "carried away"

# The paper left of and below the board: everywhere the loose peg is ever placed,
# and nowhere the board's own recesses can be mistaken for it.
TABLE_REGION = dict(x_max=430, y_min=380)


def peg_xy(bgr):
    """Centroid of the peg on the paper, or None if it is not there.

    Broad hue window on purpose: a narrow one is what made check_alignment.sh report
    the peg MISSING under warm light (see robot_learning/align_board.py).
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = (hsv[:, :, i].astype(int) for i in range(3))
    m = ((h > 60) & (h < 110) & (s > 45) & (v > 40)).astype(np.uint8)
    m[:, TABLE_REGION["x_max"]:] = 0
    m[:TABLE_REGION["y_min"], :] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, _labels, stats, cents = cv2.connectedComponentsWithStats(m, 8)
    if n < 2:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return cents[i] if stats[i, cv2.CC_STAT_AREA] > 600 else None


def gripper_closed_mask(root: Path, ep_from: int, ep_to: int, stride: int):
    """Per sampled frame, whether the jaw is in the closed part of its own range.

    Relative to the episode's own range rather than an absolute angle: the jaw's
    commanded extremes vary between runs, and what matters is whether the policy was
    holding something shut, not the number it used to do it.
    """
    df = pd.concat([pd.read_parquet(p) for p in sorted((root / "data").rglob("*.parquet"))])
    df = df.sort_values("index")
    grip = np.stack(df["observation.state"].to_numpy())[ep_from:ep_to, 5]
    if grip.size == 0:
        return np.zeros(0, dtype=bool)
    lo, hi = float(grip.min()), float(grip.max())
    threshold = lo + 0.35 * (hi - lo)
    return grip[::stride] <= threshold


def _episode_bounds(root: Path):
    meta = pd.read_parquet(root / "meta" / "episodes").sort_values("episode_index")
    return [(int(r.episode_index), int(r.dataset_from_index), int(r.dataset_to_index))
            for r in meta.itertuples()]


def track(root: Path, stride=STRIDE, first_frame_only=False):
    """{episode: [peg_xy or None, ...]} sampled every `stride` frames."""
    bounds = _episode_bounds(root)
    out = {e: [] for e, _a, _b in bounds}
    starts = {a: e for e, a, _b in bounds}
    g = 0
    for vid in sorted((root / "videos" / "observation.images.overview").rglob("*.mp4")):
        with av.open(str(vid)) as c:
            for frame in c.decode(c.streams.video[0]):
                take = (g in starts) if first_frame_only else (g % stride == 0)
                if take:
                    ep = starts.get(g) if first_frame_only else next(
                        (e for e, a, b in bounds if a <= g < b), None)
                    if ep is not None:
                        out[ep].append(peg_xy(cv2.cvtColor(
                            np.array(frame.to_image()), cv2.COLOR_RGB2BGR)))
                g += 1
    return out


def classify(samples, closed=None):
    """(outcome, start_xy, max_move_mm) for one episode's peg track."""
    seen = [p for p in samples if p is not None]
    if not seen:
        return "peg-not-found", None, 0.0
    start = seen[0]
    move = max(float(np.hypot(*(p - start))) for p in seen) * MM_PER_PX
    run = best = 0
    best_end = 0
    for i, p in enumerate(samples):
        run = run + 1 if p is None else 0
        if run > best:
            best, best_end = run, i
    if best >= GONE_SAMPLES:
        # Carried or shoved? The gripper says which.
        if closed is None or len(closed) == 0:
            return "gone-gripper-unknown", start, move
        window = closed[max(0, best_end - best):best_end + 1]
        return ("transport" if window.mean() > 0.5 else "pushed-out"), start, move
    return ("disturbed" if move > DISTURB_MM else "untouched"), start, move


def report_rollout(name: str):
    root = ROOT / "data" / "local" / "datasets" / name
    if not (root / "meta" / "episodes").exists():
        print(f"{name}: not a rollout dataset")
        return
    bounds = {e: (a, b) for e, a, b in _episode_bounds(root)}
    rows = []
    for ep, samples in track(root).items():
        a, b = bounds[ep]
        outcome, start, move = classify(samples, gripper_closed_mask(root, a, b, STRIDE))
        rows.append(dict(ep=ep, outcome=outcome, x=None if start is None else start[0],
                         y=None if start is None else start[1], moved_mm=move))
    d = pd.DataFrame(rows).sort_values("ep")
    print(f"\n=== {name}: {len(d)} episodes")
    print(f"{'ep':>3s} {'peg start':>16s} {'moved':>8s}  outcome")
    for r in d.itertuples():
        pos = "-" if r.x is None else f"({r.x:6.1f},{r.y:6.1f})"
        print(f"{r.ep:3d} {pos:>16s} {r.moved_mm:6.1f}mm  {r.outcome}")
    counts = d.outcome.value_counts().to_dict()
    print(f"  outcomes: {counts}")
    t = d[d.outcome == "transport"]
    nt = d[d.outcome.isin(["disturbed", "untouched"])]
    if len(t) and len(nt):
        print(f"  transported peg start: y mean {t.y.mean():.1f}   "
              f"not transported: y mean {nt.y.mean():.1f}")
    elif len(d.dropna(subset=["y"])):
        print(f"  peg start y: mean {d.y.mean():.1f} sd {d.y.std():.1f} "
              f"-- all episodes ended '{d.outcome.mode()[0]}', so position explains nothing here")
    return d


def report_demos(name: str, n_clusters: int = 5):
    """How the DEMOS sampled placement -- a few positions repeated, or a scatter?

    The SmolVLA reference dataset is 50 episodes over 5 cube positions, 10 each, and
    that repetition is credited with the generalization. A continuous scatter with one
    episode per position is the opposite structure at the same episode count.
    """
    root = ROOT / "data" / name
    tracks = track(root, first_frame_only=True)
    pts = np.array([t[0] for t in tracks.values() if t and t[0] is not None])
    print(f"\n=== {name}: peg start position over {len(pts)} episodes "
          f"(of {len(tracks)}; the rest occluded at frame 0)")
    if len(pts) < n_clusters:
        return
    print(f"  x {pts[:,0].mean():6.1f} +/- {pts[:,0].std():5.1f}   "
          f"y {pts[:,1].mean():6.1f} +/- {pts[:,1].std():5.1f}  "
          f"(spread {np.ptp(pts[:,0])*MM_PER_PX:.0f} x {np.ptp(pts[:,1])*MM_PER_PX:.0f} mm)")
    crit = cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1
    _c, labels, centres = cv2.kmeans(pts.astype(np.float32), n_clusters, None,
                                     crit, 10, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    print(f"  clustered into {n_clusters} groups:")
    for i, c in enumerate(centres):
        members = (labels == i).sum()
        spread = pts[labels == i]
        rad = np.hypot(*(spread - c).T).max() * MM_PER_PX if members else 0
        print(f"    ({c[0]:6.1f},{c[1]:6.1f})  {members:3d} episodes, "
              f"within {rad:4.1f}mm of the cluster centre")
    per = np.bincount(labels, minlength=n_clusters)
    print(f"  episodes per position: min {per.min()}, max {per.max()}, mean {per.mean():.1f}")
    print("  (SmolVLA's own reference dataset: 5 positions x 10 episodes each)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--demos", action="store_true",
                    help="treat the names as demo datasets under data/ instead of rollouts")
    ap.add_argument("--clusters", type=int, default=5)
    args = ap.parse_args()
    for name in args.names:
        if args.demos:
            report_demos(name, args.clusters)
        else:
            report_rollout(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
