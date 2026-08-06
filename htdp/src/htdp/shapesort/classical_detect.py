from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover - exercised via ShapesortUnavailable path
    from htdp.shapesort.errors import ShapesortUnavailable

    raise ShapesortUnavailable() from exc

# HSV bounds (OpenCV convention: H in [0,179], S/V in [0,255]). Red wraps hue 0, so it
# needs two ranges. Tuned against the synthetic fixtures in test_classical_detect.py, not
# against real camera footage yet -- expect to retune once real images exist (R1a+).
_HSV_RANGES: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] = {
    "red": [((0, 80, 60), (10, 255, 255)), ((170, 80, 60), (179, 255, 255))],
    "yellow": [((20, 80, 60), (35, 255, 255))],
    "green": [((40, 80, 60), (85, 255, 255))],
    "blue": [((90, 80, 60), (130, 255, 255))],
}

_MIN_AREA_PX = 200


@dataclass(frozen=True)
class Detection:
    cx: int
    cy: int
    angle_deg: float
    confidence: float


def _color_mask(hsv: np.ndarray, color: str) -> np.ndarray:
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in _HSV_RANGES[color]:
        mask |= cv2.inRange(hsv, np.array(lo), np.array(hi))
    return mask


def _classify_shape(contour: np.ndarray) -> str:
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
    vertices = len(approx)
    if vertices == 3:
        return "triangle"
    if vertices == 4:
        _, (w, h), _ = cv2.minAreaRect(contour)
        return "square" if 0.85 <= (w / h if h else 0) <= 1.15 else "rectangle"
    return "circle"


def _find_colored_shape_contour(image: np.ndarray, color: str, shape: str) -> np.ndarray | None:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = _color_mask(hsv, color)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = [
        c for c in contours if cv2.contourArea(c) > _MIN_AREA_PX and _classify_shape(c) == shape
    ]
    if not candidates:
        return None
    return max(candidates, key=cv2.contourArea)


def _detection_from_contour(contour: np.ndarray, image_area: int) -> Detection:
    # Use the area-moment centroid rather than the axis-aligned bounding-box center:
    # bounding-box center is not rotation-covariant (it drifts as an asymmetric shape
    # rotates, since the box re-fits to the rotated silhouette), whereas the moments
    # centroid rotates rigidly with the shape. Since this detector's job is to locate
    # arbitrarily-rotated pieces (see angle_deg), moments is the correct general choice.
    moments = cv2.moments(contour)
    cx = int(moments["m10"] / moments["m00"])
    cy = int(moments["m01"] / moments["m00"])
    _, _, angle = cv2.minAreaRect(contour)
    confidence = min(1.0, cv2.contourArea(contour) / image_area * 20)
    return Detection(cx=cx, cy=cy, angle_deg=float(angle), confidence=confidence)


def detect_piece(image: np.ndarray, color: str, shape: str) -> Detection | None:
    """Locate the piece matching (color, shape) in a frame, or None if not present.

    Used both as the fallback grasp path when SmolVLA fails, and (aliased as
    detect_hole) to locate a hole's colored outline ring -- both are colored polygonal
    regions in the frame and share the same geometric primitive.
    """
    contour = _find_colored_shape_contour(image, color, shape)
    if contour is None:
        return None
    return _detection_from_contour(contour, image.shape[0] * image.shape[1])


detect_hole = detect_piece
