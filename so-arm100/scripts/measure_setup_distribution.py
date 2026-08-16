"""Where did the demos ACTUALLY put the board and the peg?

check_alignment.sh compares against ONE reference frame and demands <5px / <12px.
If the demos themselves span more than that, the tool is asking for precision the
training data never had -- and reporting a real setup as misaligned.

Measured at the FIRST FRAME OF EVERY EPISODE, which is the only moment the peg is
placed and untouched.
"""
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "robot_learning"))
from pathlib import Path

import av, cv2, numpy as np, pandas as pd
from align_board import board_shift, peg_offset, MM_PER_PX

ref = cv2.imread("docs/reference/board_reference_demo.png")
name = sys.argv[1] if len(sys.argv) > 1 else "circle_grasp_v1"
root = Path("data") / name
meta = pd.read_parquet(root / "meta" / "episodes").sort_values("episode_index")
starts = {int(r.dataset_from_index): int(r.episode_index) for r in meta.itertuples()}
print(f"{len(starts)} episode starts in {name}")

rows = []
g = 0
for vid in sorted((root / "videos" / "observation.images.overview").rglob("*.mp4")):
    with av.open(str(vid)) as c:
        for frame in c.decode(c.streams.video[0]):
            if g in starts:
                bgr = cv2.cvtColor(np.array(frame.to_image()), cv2.COLOR_RGB2BGR)
                bdx, bdy, bresp = board_shift(ref, bgr)
                pdx, pdy, ps = peg_offset(ref, bgr)
                rows.append((starts[g], bdx, bdy, bresp, pdx, pdy, ps))
            g += 1
d = pd.DataFrame(rows, columns=["ep", "bdx", "bdy", "bresp", "pdx", "pdy", "pscore"])
print(f"measured {len(d)} episode-start frames")

b = d[d.bresp > 0.3]
print(f"\nBOARD (n={len(b)} with correlation > 0.3)")
print(f"  dx mean {b.bdx.mean():+.1f} sd {b.bdx.std():.1f}   dy mean {b.bdy.mean():+.1f} sd {b.bdy.std():.1f}")
dist = np.hypot(b.bdx, b.bdy)
print(f"  |d| from the reference frame: median {dist.median():.1f}px  p90 {dist.quantile(.9):.1f}px  max {dist.max():.1f}px")
print(f"  ({dist.median()*MM_PER_PX:.1f}mm / {dist.quantile(.9)*MM_PER_PX:.1f}mm / {dist.max()*MM_PER_PX:.1f}mm)")

p = d[d.pscore > 0.5]
print(f"\nPEG (n={len(p)} with match > 0.5)")
print(f"  dx mean {p.pdx.mean():+.1f} sd {p.pdx.std():.1f}   dy mean {p.pdy.mean():+.1f} sd {p.pdy.std():.1f}")
pd_ = np.hypot(p.pdx, p.pdy)
print(f"  |d| from the reference frame: median {pd_.median():.1f}px  p90 {pd_.quantile(.9):.1f}px  max {pd_.max():.1f}px")
print(f"  ({pd_.median()*MM_PER_PX:.1f}mm / {pd_.quantile(.9)*MM_PER_PX:.1f}mm / {pd_.max()*MM_PER_PX:.1f}mm)")

print("\nFeed these into robot_learning/align_board.py's DEMO_* constants.")
print("NOTE the sample sizes above: frames where the arm occludes the peg, or the")
print("board correlation is weak, are dropped rather than guessed at.")
