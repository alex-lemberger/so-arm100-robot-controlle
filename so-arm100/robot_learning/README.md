# SO-100 imitation-learning workspace

This folder documents the local LeRobot workflow for the downloaded
`lerobot/svla_so100_pickplace` dataset. The Python environment and model
outputs are intentionally ignored by Git.

## Environment

```bash
python3.12 -m venv .venv-lerobot
.venv-lerobot/bin/python -m pip install -U 'lerobot[dataset,training]'
```

The current machine does not expose MPS/CUDA to PyTorch, so the verified run
used CPU. Set `--policy.device=mps` or `cuda` only after confirming that the
accelerator is available.

## Train a local ACT baseline

```bash
HF_DATASETS_CACHE=.cache/hf-datasets \
.venv-lerobot/bin/lerobot-train \
  --dataset.repo_id=local/svla_so100_pickplace \
  --dataset.root=data/external/svla_so100_pickplace \
  --dataset.video_backend=pyav \
  --dataset.eval_split=0.2 \
  --policy.type=act \
  --policy.repo_id=local/act_so100_pickplace \
  --policy.push_to_hub=false \
  --policy.device=cpu \
  --output_dir=outputs/train/act_so100_pickplace \
  --job_name=act_so100_pickplace \
  --wandb.enable=false \
  --steps=500 \
  --batch_size=2 \
  --num_workers=0
```

The verified baseline is at:
`outputs/train/act_so100_pickplace_500/checkpoints/000500/pretrained_model`.

## Safety boundary

The checkpoint has only been evaluated offline. Do not connect it directly to
WebSerial. A future rollout adapter must use the saved policy processors,
Feetech calibration, action clipping, rate limiting, explicit Arm Motion
authorization, and supervised low-speed tests before any physical execution.

## Building a LeRobot dataset from recorded teleoperation episodes

Locally recorded episodes under `data/local/episodes/` go through a
three-step, human-in-the-loop pipeline before they become a LeRobot v3
dataset. Run all commands from the repo root with `.venv-lerobot`.

1. **Generate contact sheets.** Produces a per-episode review image (six
   thumbnails sampled across the episode) plus a curation manifest at
   `outputs/episode-review/curated-episodes.txt`.

   ```bash
   .venv-lerobot/bin/python3 -m robot_learning.generate_episode_contact_sheets
   ```

   Contact-sheet images regenerate freely on every run. The manifest does
   not: if `curated-episodes.txt` already exists, the script treats it as
   hand-curated and refuses to overwrite it, instead writing the current
   full episode list to `curated-episodes.txt.new`. Diff that against the
   real manifest and manually merge in any newly-recorded episodes you want
   to keep.

2. **Curate manually.** Open the contact sheets in
   `outputs/episode-review/`, then hand-edit
   `outputs/episode-review/curated-episodes.txt` — delete the line for any
   episode you want excluded from the dataset build. This step requires a
   human; nothing in the pipeline can do it for you.

3. **Build the dataset.**

   ```bash
   .venv-lerobot/bin/python3 -m robot_learning.build_lerobot_dataset
   ```

   Reads the curated manifest, validates each episode (required metadata
   keys, matching camera frame rate), and writes a LeRobot v3 dataset to
   `data/local/lerobot_dataset` using LeRobot's own writer API.

### `observation.state` caveat

Source recordings sample commanded joint targets at 20Hz, but the dataset is
built at 30fps, holding the last joint sample for intervening frames. Because
`observation.state[t] = action[t-1]`, roughly a third to a half of all frames
end up with `action[t] == action[t-1]` exactly. For that fraction of frames,
`observation.state` is a byte-for-byte copy of the action label rather than
independent information — worth knowing before training on this dataset.
