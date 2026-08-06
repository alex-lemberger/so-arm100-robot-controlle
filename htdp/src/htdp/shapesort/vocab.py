from __future__ import annotations

# Placeholder 4-hole table built from the product photo (circle/red, square/yellow,
# triangle/green, rectangle/blue outline). CONFIRM against the physical toy during R1a
# bring-up and edit this table if the real hole colors differ — open risk noted in
# docs/superpowers/specs/2026-07-08-r2-voice-shapesort-design.md.
COLOR_SHAPE_TO_HOLE: dict[tuple[str, str], str] = {
    ("red", "circle"): "hole_circle_red",
    ("yellow", "square"): "hole_square_yellow",
    ("green", "triangle"): "hole_triangle_green",
    ("blue", "rectangle"): "hole_rectangle_blue",
}

_COLORS = {color for color, _ in COLOR_SHAPE_TO_HOLE}
_SHAPES = {shape for _, shape in COLOR_SHAPE_TO_HOLE}


def parse_target(text: str) -> str | None:
    """Extract a known (color, shape) pair from free text and map it to a hole id.

    Returns None rather than guessing when the text does not contain exactly one known
    color word and one known shape word — the orchestrator (Task 4) treats None as an
    ASR-miss and asks again instead of acting on an ambiguous command.
    """
    words = text.lower().split()
    colors_found = [w for w in words if w in _COLORS]
    shapes_found = [w for w in words if w in _SHAPES]
    if len(colors_found) != 1 or len(shapes_found) != 1:
        return None
    return COLOR_SHAPE_TO_HOLE.get((colors_found[0], shapes_found[0]))
