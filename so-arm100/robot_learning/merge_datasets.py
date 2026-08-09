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
import json
import logging
import shutil
import sys
from pathlib import Path

from lerobot.datasets.aggregate import aggregate_datasets

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS = REPO_ROOT / "data" / "local" / "datasets"
# Normalised copies live here so a merge never mutates a source dataset.
TMP = DATASETS / ".merge_tmp"


def _features(root: Path) -> dict:
    return json.loads((root / "meta" / "info.json").read_text())["features"]


def _column_is_constant(root: Path, column: str) -> tuple[bool, object]:
    """Is `column` the same value in every frame of the dataset?"""
    import pandas as pd

    values = set()
    for parquet in sorted((root / "data").rglob("*.parquet")):
        series = pd.read_parquet(parquet, columns=[column])[column]
        values.update(series.map(lambda v: v.item() if hasattr(v, "item") else v).unique().tolist())
        if len(values) > 1:
            return False, None
    return True, (values.pop() if values else None)


def harmonise(names: list[str], roots: list[Path]) -> list[Path]:
    """Drop features that are not present in every source dataset.

    `aggregate_datasets` requires identical feature sets (`validate_all_metadata`),
    and DAgger datasets carry one the demonstrations do not: `intervention`, added
    by rollout/context.py:347. Without this, merging corrections into demos fails.

    Dropping is safe when the extra column is constant, which it is in the default
    corrections-only mode -- every recorded frame is an intervention, so the flag
    says nothing that "which dataset did this episode come from" does not. Under
    --record-autonomous it varies, and dropping would discard the tags that
    distinguish corrections from autonomous frames, so that case stops instead.

    Only the dataset carrying the extra column is rewritten, never the others: the
    corrections are a few hundred frames, the demonstrations are hundreds of MB.
    """
    from lerobot.datasets.dataset_tools import remove_feature
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    per_dataset = {name: set(_features(root)) for name, root in zip(names, roots, strict=True)}
    common = set.intersection(*per_dataset.values())

    out_roots = []
    for name, root in zip(names, roots, strict=True):
        extra = sorted(per_dataset[name] - common)
        if not extra:
            out_roots.append(root)
            continue

        for column in extra:
            constant, value = _column_is_constant(root, column)
            if not constant:
                sys.exit(
                    f"'{name}' has feature '{column}' that the other datasets lack, and it "
                    f"varies between frames -- dropping it would lose information.\n"
                    f"This happens with --record-autonomous, where `intervention` marks which "
                    f"frames are corrections. Merge those separately, or re-record without it."
                )
            print(f"  {name}: dropping '{column}' (constant {value!r}; the other datasets lack it)")

        dst = TMP / name
        if dst.exists():
            shutil.rmtree(dst)
        remove_feature(
            LeRobotDataset(f"local/{name}", root=root),
            feature_names=extra,
            output_dir=dst,
            repo_id=f"local/{name}_harmonised",
        )
        out_roots.append(dst)

    return out_roots


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

    # DAgger datasets carry an `intervention` column the demonstrations lack;
    # aggregate_datasets rejects mismatched feature sets outright.
    merge_roots = harmonise(args.sources, roots)

    try:
        aggregate_datasets(
            repo_ids=[f"local/{name}" for name in args.sources],
            roots=merge_roots,
            aggr_repo_id=f"local/{args.into}",
            aggr_root=dst,
        )
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)

    print(f"\nMerged -> {dst}")
    print(f"Train on it with:  python robot_learning/loop.py train --dataset={args.into} ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
