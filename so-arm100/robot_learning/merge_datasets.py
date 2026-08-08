"""Merge LeRobot datasets into one trainable dataset.

Needed because `lerobot-train` takes a single dataset: `DatasetConfig.repo_id`
is a plain `str`, and `datasets/factory.py` raises
`NotImplementedError("The MultiLeRobotDataset isn't supported for now.")`.
So demonstrations and DAgger corrections, which are collected into separate
datasets, have to be merged on disk before a fine-tune can see both.

That is exactly what `hil_data_collection.mdx` prescribes: "Fine-tune on the
**combined** dataset (demo-dataset + hil-dataset merged together)."

The merge itself is LeRobot's own `aggregate_datasets`. Do not hand-roll it.
In the v3.0 layout an episode is not a file -- many episodes share one parquet
shard and one mp4, and `meta/episodes/*.parquet` locates each by row range
(`dataset_from_index`/`dataset_to_index`) and by video time window
(`from_timestamp`/`to_timestamp`). Merging means re-indexing every episode,
shifting every video timestamp by the accumulated duration, re-packing shards
to their size limits, unifying the task table, and recomputing aggregate stats.
`aggregate_datasets` does all of it.

Sources must agree on fps, robot_type and features, or `validate_all_metadata`
raises. Datasets written by `lerobot-record` and by `lerobot-rollout`
(which is what `loop.py dagger` runs) do agree -- verified 2026-08-09 against
circle_insert_50ep_trimmed and rollout_trimmed_b32.

Usually invoked as `python robot_learning/loop.py merge`; runnable by hand:

    ~/lerobot/.venv/bin/python robot_learning/merge_datasets.py \
        --into circle_insert_dagger_v1 circle_insert_50ep_trimmed dagger_v1
"""

import argparse
import logging
import sys
from pathlib import Path

from lerobot.datasets.aggregate import aggregate_datasets

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS = REPO_ROOT / "data" / "local" / "datasets"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("sources", nargs="+", help="dataset names under data/local/datasets")
    parser.add_argument("--into", required=True, help="name of the merged dataset to write")
    args = parser.parse_args()

    if len(args.sources) < 2:
        sys.exit("Merging needs at least two source datasets.")

    roots = [DATASETS / name for name in args.sources]
    for name, root in zip(args.sources, roots, strict=True):
        if not root.exists():
            sys.exit(f"No dataset at {root} (source '{name}').")

    dst = DATASETS / args.into
    if dst.exists():
        # aggregate_datasets would fail partway through on an existing root,
        # leaving a half-written dataset that still looks loadable.
        sys.exit(f"{dst} already exists. Remove it or choose another --into name.")

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    aggregate_datasets(
        repo_ids=[f"local/{name}" for name in args.sources],
        roots=roots,
        aggr_repo_id=f"local/{args.into}",
        aggr_root=dst,
    )

    print(f"\nMerged -> {dst}")
    print(f"Train on it with:  python robot_learning/loop.py train --dataset={args.into} ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
