from __future__ import annotations

import math
from collections.abc import Sequence


def matrix_to_pos_quat(
    m: Sequence[Sequence[float]],
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """Convert an OpenVR 3x4 rigid transform to (position, quaternion wxyz).

    ``m`` is row-major: ``m[r][c]`` with r in 0..2, c in 0..3. The translation is
    the last column; the rotation is the leading 3x3. Uses Shepperd's method
    (picks the largest pivot for numerical stability) and returns a unit quaternion.
    """
    pos = (float(m[0][3]), float(m[1][3]), float(m[2][3]))

    r00, r01, r02 = m[0][0], m[0][1], m[0][2]
    r10, r11, r12 = m[1][0], m[1][1], m[1][2]
    r20, r21, r22 = m[2][0], m[2][1], m[2][2]
    trace = r00 + r11 + r22

    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (r21 - r12) / s
        y = (r02 - r20) / s
        z = (r10 - r01) / s
    elif r00 > r11 and r00 > r22:
        s = math.sqrt(1.0 + r00 - r11 - r22) * 2.0
        w = (r21 - r12) / s
        x = 0.25 * s
        y = (r01 + r10) / s
        z = (r02 + r20) / s
    elif r11 > r22:
        s = math.sqrt(1.0 + r11 - r00 - r22) * 2.0
        w = (r02 - r20) / s
        x = (r01 + r10) / s
        y = 0.25 * s
        z = (r12 + r21) / s
    else:
        s = math.sqrt(1.0 + r22 - r00 - r11) * 2.0
        w = (r10 - r01) / s
        x = (r02 + r20) / s
        y = (r12 + r21) / s
        z = 0.25 * s

    n = math.sqrt(w * w + x * x + y * y + z * z)
    return pos, (w / n, x / n, y / n, z / n)


def tracking_to_quality(pose_is_valid: bool, tracking_result: int, ok_result: int) -> float:
    """Binary validity flag: 1.0 only when the pose is valid AND tracking is OK."""
    return 1.0 if (pose_is_valid and tracking_result == ok_result) else 0.0
