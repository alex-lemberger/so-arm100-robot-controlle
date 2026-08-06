import math

import pytest

from htdp.ingest.frame import IDENTITY, quat_mul, rotate_vector


def test_quat_mul_identity_left_and_right():
    q = (0.0, 0.0, 1.0, 0.0)
    assert quat_mul(IDENTITY, q) == pytest.approx(q)
    assert quat_mul(q, IDENTITY) == pytest.approx(q)


def test_rotate_vector_identity_is_noop():
    assert rotate_vector(IDENTITY, (1.0, 2.0, 3.0)) == pytest.approx((1.0, 2.0, 3.0))


def test_rotate_vector_90deg_about_z_maps_x_to_y():
    rot = (math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))
    assert rotate_vector(rot, (1.0, 0.0, 0.0)) == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)


def test_rotate_vector_inverse_round_trips():
    rot = (math.cos(math.pi / 6), 0.0, math.sin(math.pi / 6), 0.0)  # 60° about y
    inv = (rot[0], -rot[1], -rot[2], -rot[3])
    v = (0.3, -0.7, 1.2)
    assert rotate_vector(inv, rotate_vector(rot, v)) == pytest.approx(v, abs=1e-9)


def test_apply_transform_identity_is_noop():
    from htdp.ingest.frame import apply_transform

    pos, quat = apply_transform(IDENTITY, (1.0, 2.0, 3.0), (1.0, 0.0, 0.0, 0.0))
    assert pos == pytest.approx((1.0, 2.0, 3.0))
    assert quat == pytest.approx((1.0, 0.0, 0.0, 0.0))


def test_apply_transform_90deg_about_z():
    from htdp.ingest.frame import apply_transform

    rot = (math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))
    pos, quat = apply_transform(rot, (1.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    assert pos == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)
    assert quat == pytest.approx(rot, abs=1e-9)  # rot ⊗ identity == rot
