"""One-off: prep a DAgger correction dataset for merging into circle_grasp_v1_*.

Two schema gaps between rollout_dagger_<tag> and the training datasets (A/B/C,
all built from the app-recording pipeline, overview camera only):
  - missing episode_source_type_id (provenance tag from scripts/export_lerobot_dataset.py,
    only present on the mixed real+synthetic set) -- add it as REAL_HUMAN (0).
  - extra observation.images.wrist -- cmd_dagger/cmd_eval record whatever
    CONFIG['cameras'] has configured on the robot (both), but the checkpoints
    being corrected only ever consumed observation.images.overview. Drop it so
    the merged dataset matches what the policy actually trains on.
"""
import sys
from pathlib import Path

import numpy as np
from lerobot.datasets.dataset_tools import add_features, remove_feature
from lerobot.datasets.lerobot_dataset import LeRobotDataset

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS = REPO_ROOT / "data" / "local" / "datasets"

name = sys.argv[1]
root = DATASETS / name

ds = LeRobotDataset(f"local/{name}", root=root)
no_wrist_name = f"{name}_nowrist"
ds = remove_feature(ds, "observation.images.wrist", output_dir=DATASETS / no_wrist_name, repo_id=f"local/{no_wrist_name}")

out_name = f"{name}_tagged"
out_root = DATASETS / out_name
values = np.zeros((len(ds), 1), dtype=np.int64)
features = {"episode_source_type_id": (values, {"dtype": "int64", "shape": (1,), "names": None})}
add_features(ds, features, output_dir=out_root, repo_id=f"local/{out_name}")
print(f"wrote {out_root}")
