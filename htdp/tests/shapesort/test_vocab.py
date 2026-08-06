from __future__ import annotations

import pytest

from htdp.shapesort.vocab import COLOR_SHAPE_TO_HOLE, parse_target


def test_parse_target_matches_color_and_shape() -> None:
    assert parse_target("put the green triangle into the box") == "hole_triangle_green"


def test_parse_target_case_insensitive() -> None:
    assert parse_target("PUT THE RED CIRCLE IN THE BOX") == "hole_circle_red"


def test_parse_target_ignores_extra_words() -> None:
    assert parse_target("please gently place the yellow square somewhere") == "hole_square_yellow"


def test_parse_target_unknown_color_returns_none() -> None:
    assert parse_target("put the purple triangle in the box") is None


def test_parse_target_unknown_shape_returns_none() -> None:
    assert parse_target("put the green pentagon in the box") is None


def test_parse_target_no_recognizable_phrase_returns_none() -> None:
    assert parse_target("what time is it") is None


@pytest.mark.parametrize("hole_id", list(COLOR_SHAPE_TO_HOLE.values()))
def test_every_hole_id_is_unique(hole_id: str) -> None:
    assert list(COLOR_SHAPE_TO_HOLE.values()).count(hole_id) == 1
