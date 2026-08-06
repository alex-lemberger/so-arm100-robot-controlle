from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("cv2")
pytest.importorskip("PIL")

from PIL import Image, ImageDraw

from htdp.shapesort.classical_detect import Detection, detect_hole, detect_piece

CANVAS = 200

_RGB = {
    "red": (220, 30, 30),
    "yellow": (230, 210, 20),
    "green": (30, 180, 60),
    "blue": (30, 90, 220),
}


def _blank_canvas() -> Image.Image:
    return Image.new("RGB", (CANVAS, CANVAS), (200, 200, 200))


def _rotated_square_points(cx: float, cy: float, half: float, deg: float) -> list[tuple[float, float]]:
    corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    rad = math.radians(deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return [(cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a) for x, y in corners]


def _draw_square(draw: ImageDraw.ImageDraw, color: str, cx: float, cy: float, half: float, deg: float) -> None:
    draw.polygon(_rotated_square_points(cx, cy, half, deg), fill=_RGB[color])


def _draw_triangle(draw: ImageDraw.ImageDraw, color: str, cx: float, cy: float, size: float) -> None:
    pts = [(cx, cy - size), (cx - size, cy + size), (cx + size, cy + size)]
    draw.polygon(pts, fill=_RGB[color])


def _draw_circle(draw: ImageDraw.ImageDraw, color: str, cx: float, cy: float, r: float) -> None:
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_RGB[color])


def _to_bgr(img: Image.Image) -> np.ndarray:
    arr = np.array(img)  # HWC, RGB
    return arr[:, :, ::-1].copy()  # BGR for cv2


def test_detect_piece_finds_single_shape() -> None:
    img = _blank_canvas()
    draw = ImageDraw.Draw(img)
    _draw_triangle(draw, "red", 100, 100, 40)
    det = detect_piece(_to_bgr(img), "red", "triangle")
    assert det is not None
    assert abs(det.cx - 100) <= 4
    # 113.33 is the triangle's true area centroid (average of its three vertices:
    # (100,60), (60,140), (140,140)), not an approximation -- do not "fix" this back
    # to 100. The moments centroid is rotation-covariant, unlike a bounding-box center,
    # which is why detection uses cv2.moments() rather than cv2.boundingRect().
    assert abs(det.cy - 113) <= 4
    assert det.confidence > 0.0


def test_detect_piece_picks_correct_target_among_distractors() -> None:
    img = _blank_canvas()
    draw = ImageDraw.Draw(img)
    _draw_triangle(draw, "red", 40, 40, 25)
    _draw_square(draw, "blue", 150, 60, 25, 0)
    _draw_circle(draw, "yellow", 60, 150, 25)
    det = detect_piece(_to_bgr(img), "blue", "square")
    assert det is not None
    assert abs(det.cx - 150) <= 4
    assert abs(det.cy - 60) <= 4


def test_detect_piece_returns_none_when_target_absent() -> None:
    img = _blank_canvas()
    draw = ImageDraw.Draw(img)
    _draw_triangle(draw, "red", 100, 100, 40)
    det = detect_piece(_to_bgr(img), "green", "triangle")
    assert det is None


def test_detect_piece_tracks_relative_rotation() -> None:
    def angle_diff_mod90(a: float, b: float) -> float:
        d = abs(a - b) % 90
        return min(d, 90 - d)

    img0 = _blank_canvas()
    _draw_square(ImageDraw.Draw(img0), "blue", 100, 100, 30, 0)
    det0 = detect_piece(_to_bgr(img0), "blue", "square")
    assert det0 is not None

    img1 = _blank_canvas()
    _draw_square(ImageDraw.Draw(img1), "blue", 100, 100, 30, 25)
    det1 = detect_piece(_to_bgr(img1), "blue", "square")
    assert det1 is not None

    # The two detected angles should differ by ~25 degrees (mod 90, since a square has
    # 4-fold rotational symmetry and cv2's minAreaRect angle convention isn't fixed
    # across versions) -- this is robust to that convention instead of hardcoding it.
    assert angle_diff_mod90(det0.angle_deg + 25, det1.angle_deg) < 5.0


def test_detect_hole_is_same_detector_as_detect_piece() -> None:
    img = _blank_canvas()
    _draw_circle(ImageDraw.Draw(img), "red", 100, 100, 30)
    det = detect_hole(_to_bgr(img), "red", "circle")
    assert det is not None
    assert detect_hole is detect_piece
