#!/bin/bash
# Train the DEPLOYMENT checkpoint for the circle-insert task.
#
# Deliberately separate from robot_learning/train_sim_real_ratio.py: that script
# is bound to the frozen sim/real ratio experiment (47 real episodes, a 12-episode
# holdout, 20k steps) and must stay reproducible. That experiment is finished and
# its answer was "real only". This is the checkpoint meant to actually run on the
# arm, so it differs in exactly two ways, both deliberate:
#
#   * all 59 real episodes, not the experiment's 47. The 12 held-out episodes
#     existed to score the ratio sweep; that sweep is over. 47 was below the ~50
#     episodes/task floor this task is documented to need.
#   * 30000 steps, matching scheduler_decay_steps. The sweep stopped at 20000
#     against a schedule configured to decay over 30000, so every one of those
#     checkpoints was frozen mid-decay and never got the low-LR phase where fine
#     positioning converges.
#
# Same base snapshot, optimiser, batch size and rename map as the sweep, so the
# comparison against real_only stays meaningful.
#
#   ./train_deploy.sh [--steps N] [--tag NAME] [--dataset DIRNAME]
#
# --dataset names a directory under data/local/datasets (repo id local/<name>).
# It defaults to the 59-episode set this script was written for; the 80-episode
# set adds the 2026-08-20 batch, recorded because much of the 08-17 batch was
# stopped before the place phase.
set -e
cd "$(dirname "$0")"

STEPS=30000
TAG=circle_insert_real59_30k
DATASET=circle_insert_topcam_59_trimmed
EPISODES=""
while [ $# -gt 0 ]; do
  case "$1" in
    --steps) STEPS="$2"; shift 2 ;;
    --tag)   TAG="$2"; shift 2 ;;
    --dataset) DATASET="$2"; shift 2 ;;
    # Subset of episode indices, e.g. the ones that actually run through to a
    # seated release. 27 of the 60 raw recordings were stopped after the grasp,
    # so they end with the arm holding the peg and motionless -- which is also
    # the failure the policy shows on the bench.
    --episodes) EPISODES="$2"; shift 2 ;;
    *) echo "unknown argument $1"; exit 1 ;;
  esac
done

CFG=configs/sim_real_ratio_training.json
REV=$(python3 -c "import json;print(json.load(open('$CFG'))['policy']['revision'])")
IMG=$(python3 -c "import json;print(json.load(open('$CFG'))['runtime']['docker_image_label'])")
SNAP="/hf-cache/hub/models--lerobot--smolvla_base/snapshots/$REV"
OUT="outputs/train/$TAG"
[ -e "$OUT" ] && { echo "refusing to overwrite $OUT"; exit 1; }

DATASET_ROOT="data/local/datasets/$DATASET"
[ -d "$DATASET_ROOT" ] || { echo "no dataset at $DATASET_ROOT"; exit 1; }
EPISODE_COUNT=$(python3 -c "import json;print(json.load(open('$DATASET_ROOT/meta/info.json'))['total_episodes'])")

EP_ARG=""
if [ -n "$EPISODES" ]; then
  EP_ARG="--dataset.episodes=$EPISODES"
  echo "training $TAG: $DATASET episode subset $EPISODES, $STEPS steps, decay matched"
else
  echo "training $TAG: all $EPISODE_COUNT episodes of $DATASET, $STEPS steps, decay matched"
fi
exec docker run --rm --gpus all --ipc=host \
  -e HOME=/tmp/lerobot-home -e USER=lerobot -e LOGNAME=lerobot \
  -e HF_HOME=/hf-cache -e PYTHONUNBUFFERED=1 \
  -v "$(pwd)/..:$(pwd)/.." \
  -v "$HOME/.cache/huggingface:/hf-cache" \
  -w "$(pwd)" "$IMG" \
  lerobot-train \
  --dataset.repo_id="local/$DATASET" \
  --dataset.root="$DATASET_ROOT" \
  $EP_ARG \
  --dataset.video_backend=pyav \
  --dataset.eval_split=0.0 \
  --dataset.image_transforms.enable=false \
  --dataset.return_uint8=false \
  --policy.path="$SNAP" \
  --policy.push_to_hub=false \
  --policy.device=cuda \
  --policy.use_amp=false \
  --policy.empty_cameras=1 \
  --policy.optimizer_lr=0.0001 \
  --policy.optimizer_betas='[0.9,0.95]' \
  --policy.optimizer_eps=1e-08 \
  --policy.optimizer_weight_decay=1e-10 \
  --policy.optimizer_grad_clip_norm=10 \
  --policy.scheduler_warmup_steps=1000 \
  --policy.scheduler_decay_steps="$STEPS" \
  --policy.scheduler_decay_lr=2.5e-06 \
  --rename_map='{"observation.images.overview":"observation.images.camera1","observation.images.wrist":"observation.images.camera2"}' \
  --seed=20260817 --cudnn_deterministic=true \
  --batch_size=24 --num_workers=4 \
  --steps="$STEPS" --save_freq=5000 --log_freq=100 \
  --eval_steps=0 --env_eval_freq=0 --wandb.enable=false \
  --output_dir="$OUT" --job_name="$TAG"
