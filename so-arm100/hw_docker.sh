#!/bin/bash
# Canonical docker invocation for anything that touches the real robot
# (loop.py eval/dagger/record/build/merge). Every hardware script should call
# this instead of hand-writing `docker run` -- the device/mount flags below
# are the single source of truth. If a port ever re-maps (not stable across
# reboots/replugs -- run ./verify_ports.sh) or a mount/device needs to
# change, fix it here once instead of in N copy-pasted scripts.
set -e
cd "$(dirname "$0")"
# -t only when there really is a terminal: eval/dagger need it for their live
# keyboard controls, but non-interactive callers (alignment checks, scripted
# diagnostics) would die on "the input device is not a TTY".
TTY_FLAGS="-i"
[ -t 0 ] && TTY_FLAGS="-it"
exec docker run --rm --gpus all $TTY_FLAGS \
  --device=/dev/ttyACM0 --device=/dev/ttyACM1 \
  --device=/dev/video0 --device=/dev/video2 \
  -v "$HOME/.cache/huggingface/lerobot/calibration:/root/.cache/huggingface/lerobot/calibration" \
  -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" \
  lerobot-train:latest \
  "$@"
