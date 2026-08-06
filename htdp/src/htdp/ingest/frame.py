from __future__ import annotations

Quat = tuple[float, float, float, float]  # w, x, y, z
Vec3 = tuple[float, float, float]

IDENTITY: Quat = (1.0, 0.0, 0.0, 0.0)


def quat_mul(a: Quat, b: Quat) -> Quat:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def _conj(q: Quat) -> Quat:
    w, x, y, z = q
    return (w, -x, -y, -z)


def rotate_vector(q: Quat, v: Vec3) -> Vec3:
    p: Quat = (0.0, v[0], v[1], v[2])
    r = quat_mul(quat_mul(q, p), _conj(q))
    return (r[1], r[2], r[3])


def apply_transform(rotation: Quat, pos: Vec3, quat: Quat) -> tuple[Vec3, Quat]:
    """Rotate a position vector and compose orientation into the contract frame."""
    return rotate_vector(rotation, pos), quat_mul(rotation, quat)
