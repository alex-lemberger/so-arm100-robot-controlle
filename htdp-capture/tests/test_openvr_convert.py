import math

from htdp_capture.openvr_convert import matrix_to_pos_quat, tracking_to_quality

_SQRT_HALF = math.sqrt(0.5)


def _approx(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def test_identity_matrix_is_origin_and_identity_quat():
    m = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]
    pos, quat = matrix_to_pos_quat(m)
    assert pos == (0.0, 0.0, 0.0)
    assert _approx(quat, (1.0, 0.0, 0.0, 0.0))


def test_translation_column_is_extracted():
    m = [[1.0, 0.0, 0.0, 1.5], [0.0, 1.0, 0.0, -2.0], [0.0, 0.0, 1.0, 3.25]]
    pos, _ = matrix_to_pos_quat(m)
    assert pos == (1.5, -2.0, 3.25)


def test_90_deg_about_z():
    # rotation 90 deg about +z, translation (1,2,3)
    m = [[0.0, -1.0, 0.0, 1.0], [1.0, 0.0, 0.0, 2.0], [0.0, 0.0, 1.0, 3.0]]
    pos, quat = matrix_to_pos_quat(m)
    assert pos == (1.0, 2.0, 3.0)
    assert _approx(quat, (_SQRT_HALF, 0.0, 0.0, _SQRT_HALF))


def test_180_deg_about_x_hits_diagonal_branch():
    m = [[1.0, 0.0, 0.0, 0.0], [0.0, -1.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.0]]
    _, quat = matrix_to_pos_quat(m)
    assert _approx(quat, (0.0, 1.0, 0.0, 0.0))


def test_quaternion_is_unit_norm():
    m = [[0.0, -1.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]
    _, quat = matrix_to_pos_quat(m)
    assert abs(math.sqrt(sum(c * c for c in quat)) - 1.0) <= 1e-9


def test_quality_valid_and_ok_is_one():
    assert tracking_to_quality(True, 200, 200) == 1.0


def test_quality_valid_but_not_ok_is_zero():
    assert tracking_to_quality(True, 201, 200) == 0.0


def test_quality_invalid_is_zero():
    assert tracking_to_quality(False, 200, 200) == 0.0
