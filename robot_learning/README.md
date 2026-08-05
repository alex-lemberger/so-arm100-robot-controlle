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
