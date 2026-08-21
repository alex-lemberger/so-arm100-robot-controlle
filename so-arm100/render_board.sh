#!/bin/bash
# Render the board close up from three angles, headless (scripts/render_board_views.py).
# The headless counterpart to view_scene.sh: no X server, PNGs instead of a window.
#
#   ./render_board.sh                     # writes board_views/board_{top,oblique,grazing}.png
#   ./render_board.sh --light-scale 0.75
set -e
cd "$(dirname "$0")"
exec ./sim_docker.sh scripts/render_board_views.py "$@"
