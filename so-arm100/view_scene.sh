#!/bin/bash
# Open the Isaac scene in a window (scripts/view_scene.py). Same scene the
# exporter builds, with a camera you can fly.
#
# This is sim_docker.sh plus X11 passthrough -- kept separate because the GUI
# flags are useless (and the Xauthority mount is a needless privilege) for every
# headless run, which is all the others.
set -e
cd "$(dirname "$0")"

if [ -z "$DISPLAY" ]; then
  echo "DISPLAY is not set -- there is no X server to draw into." >&2
  exit 1
fi

# Prefer passing the real Xauthority cookie over loosening access control with
# `xhost +local:docker`, which stays loosened for the rest of the session.
XAUTH_ARGS=()
if [ -n "$XAUTHORITY" ] && [ -f "$XAUTHORITY" ]; then
  XAUTH_ARGS=(-e "XAUTHORITY=$XAUTHORITY" -v "$XAUTHORITY:$XAUTHORITY:ro")
fi

# -t only when there really is a terminal. Same trap hw_docker.sh documents: a
# non-interactive caller dies on "cannot attach stdin to a TTY-enabled container".
TTY_FLAGS="-i"
[ -t 0 ] && TTY_FLAGS="-it"

exec docker run --rm $TTY_FLAGS --gpus all \
  -e "DISPLAY=$DISPLAY" \
  "${XAUTH_ARGS[@]}" \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v "$(pwd)/..:$(pwd)/.." \
  -v /media/alex/F6E48479E4843DBD/Users:/media/alex/F6E48479E4843DBD/Users:ro \
  -w "$(pwd)" \
  leisaac-sim:latest \
  /workspace/isaaclab/_isaac_sim/python.sh scripts/view_scene.py "$@"
