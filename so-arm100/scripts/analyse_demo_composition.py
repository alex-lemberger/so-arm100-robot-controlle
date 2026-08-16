"""What is actually IN the demonstrations, by behaviour rather than by episode count.

Episode counts say a dataset is big. They say nothing about whether the behaviour a
policy fails at is in there in any quantity -- and on this task it is not. The two
failure modes measured on hardware (fails at gripper closure; transports to the board
and never opens) correspond to the two moments the gripper actuates, and those are a
few percent of the frames. Half the rest is the arm holding still.

That is a dataset-COMPOSITION problem, and it is invisible to every count in
meta/info.json. Re-run this after collecting corrective demos: the question is not
"how many episodes did we add" but "did the share of the failing behaviour move".

    ./analyse_demos.sh                       # every real dataset under data/
    ./analyse_demos.sh circle_grasp_v1
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# A joint step below this (degrees per frame, so 7.5 deg/s at 30Hz) is the arm holding
# position rather than moving. A gripper step beyond GRIP_DEG is it actuating.
MOVE_DEG = 0.25
GRIP_DEG = 0.5


def episodes(root: Path):
    df = pd.concat([pd.read_parquet(p) for p in sorted((root / "data").rglob("*.parquet"))])
    meta = pd.read_parquet(root / "meta" / "episodes")
    tasks = {int(r.episode_index): (r.tasks[0] if isinstance(r.tasks, (list, np.ndarray)) else r.tasks)
             for r in meta.itertuples()}
    for idx, g in df.groupby("episode_index"):
        g = g.sort_values("frame_index")
        yield int(idx), tasks.get(int(idx), "?"), np.stack(g["observation.state"].to_numpy())


def analyse(root: Path):
    rows = []
    for idx, task, state in episodes(root):
        arm, grip = state[:, :5], state[:, 5]
        step = np.abs(np.diff(arm, axis=0)).max(axis=1)
        gd = np.diff(grip)
        moving = step > MOVE_DEG
        n = len(state)
        rows.append(dict(
            episode=idx, task=task, frames=n,
            closing=int((gd < -GRIP_DEG).sum()),
            opening=int((gd > GRIP_DEG).sum()),
            still=int((~moving).sum()),
            lead_in_still=int(np.argmax(moving)) if moving.any() else n,
            tail_still=n - 1 - int(len(moving) - 1 - np.argmax(moving[::-1])) if moving.any() else n,
        ))
    return pd.DataFrame(rows)


def report(name: str, d: pd.DataFrame) -> None:
    total = d.frames.sum()
    print(f"\n=== {name}: {len(d)} episodes, {total} frames")
    print(f"  gripper CLOSING {d.closing.sum():6d} frames ({100*d.closing.sum()/total:5.2f}%)   "
          f"<- the 'fails at closure' failure mode lives here")
    print(f"  gripper OPENING {d.opening.sum():6d} frames ({100*d.opening.sum()/total:5.2f}%)   "
          f"<- the 'never releases' failure mode lives here")
    print(f"  arm HOLDING STILL {d.still.sum():6d} frames ({100*d.still.sum()/total:5.1f}%)")
    for task, sub in d.groupby("task"):
        t = sub.frames.sum()
        print(f"    [{task[:44]:44s}] {len(sub):3d} eps {t:6d} fr  "
              f"close {100*sub.closing.sum()/t:5.2f}%  open {100*sub.opening.sum()/t:5.2f}%  "
              f"still {100*sub.still.sum()/t:4.1f}%  median len {sub.frames.median():.0f} "
              f"(dead lead-in {sub.lead_in_still.median():.0f}, tail {sub.tail_still.median():.0f})")


def main() -> int:
    names = sys.argv[1:] or [p.name for p in sorted((ROOT / "data").iterdir())
                             if (p / "meta" / "episodes").exists()]
    for name in names:
        root = ROOT / "data" / name
        if not (root / "meta" / "episodes").exists():
            print(f"{name}: no meta/episodes -- not a LeRobot dataset, skipping")
            continue
        report(name, analyse(root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
