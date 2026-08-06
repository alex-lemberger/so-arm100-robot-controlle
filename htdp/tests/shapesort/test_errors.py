from __future__ import annotations

from htdp.shapesort.errors import ShapesortUnavailable


def test_shapesort_unavailable_default_message() -> None:
    err = ShapesortUnavailable()
    assert "uv sync --extra shapesort" in str(err)


def test_shapesort_unavailable_is_runtime_error() -> None:
    assert issubclass(ShapesortUnavailable, RuntimeError)
