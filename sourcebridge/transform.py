"""Explicit coordinate spaces and small rigid-transform helpers.

Source 1 model space and s&box (Source 2) model space are both Z-up, X-forward, inches.
SMD files are written in Source 1 model space and imported by ModelDoc with import_scale 1.0,
so no unit or axis change is applied to geometry, bones, attachments or physics. The only
conversion in the pipeline is IVP (physics) space -> model space, done in formats/phy.py.
This single decision is recorded in every AssetDocument (see TRANSFORMS).
"""

from __future__ import annotations

import math

TRANSFORMS = {
    "source_space": "Source 1 model space: Z-up, X-forward, right-handed, units = inches",
    "target_space": "s&box ModelDoc model space: Z-up, X-forward, units = inches",
    "geometry": "identity (SMD in source space, ModelDoc import_scale 1.0, no rotation)",
    "physics": "IVP metres (x, -z, y) converted to inches in model/bone space, then identity",
    "uv": "VVD stores v flipped (1 - v); SMD output flips back so ModelDoc sees authoring UVs",
    "status": "identity assumption verified against Facepunch examples only for FBX; the SMD path "
    "is confirmed once the s&box target test passes (docs/target-tests.md)",
}

Mat34 = tuple[float, ...]  # row-major 3x4


def mat34_inverse(m: Mat34) -> Mat34:
    """Inverse of an affine 3x4 matrix (general 3x3 part)."""
    a, b, c, tx, d, e, f, ty, g, h, i, tz = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        raise ValueError("singular bone matrix")
    inv = [
        (e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det,
        (f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det,
        (d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det,
    ]  # fmt: skip
    t = (
        -(inv[0] * tx + inv[1] * ty + inv[2] * tz),
        -(inv[3] * tx + inv[4] * ty + inv[5] * tz),
        -(inv[6] * tx + inv[7] * ty + inv[8] * tz),
    )
    return (inv[0], inv[1], inv[2], t[0], inv[3], inv[4], inv[5], t[1], inv[6], inv[7], inv[8], t[2])


def mat34_apply(m: Mat34, p: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = p
    return (
        m[0] * x + m[1] * y + m[2] * z + m[3],
        m[4] * x + m[5] * y + m[6] * z + m[7],
        m[8] * x + m[9] * y + m[10] * z + m[11],
    )


def mat34_mul(a: Mat34, b: Mat34) -> Mat34:
    out = []
    for r in range(3):
        for col in range(4):
            v = sum(a[r * 4 + k] * b[k * 4 + col] for k in range(3))
            if col == 3:
                v += a[r * 4 + 3]
            out.append(v)
    return tuple(out)


def quat_to_mat34(q: tuple[float, float, float, float], pos: tuple[float, float, float]) -> Mat34:
    x, y, z, w = q
    return (
        1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), pos[0],
        2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), pos[1],
        2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), pos[2],
    )  # fmt: skip


def euler_to_quat(rot: tuple[float, float, float]) -> tuple[float, float, float, float]:
    """Source RadianEuler (x=roll, y=pitch, z=yaw) -> quaternion (x, y, z, w), as AngleQuaternion."""
    sr, cr = math.sin(rot[0] * 0.5), math.cos(rot[0] * 0.5)
    sp, cp = math.sin(rot[1] * 0.5), math.cos(rot[1] * 0.5)
    sy, cy = math.sin(rot[2] * 0.5), math.cos(rot[2] * 0.5)
    srxcp, crxsp = sr * cp, cr * sp
    crxcp, srxsp = cr * cp, sr * sp
    return (
        srxcp * cy - crxsp * sy,
        crxsp * cy + srxcp * sy,
        crxcp * sy - srxsp * cy,
        crxcp * cy + srxsp * sy,
    )


def bone_world_matrices(bones) -> list[Mat34]:
    """Bind-pose bone-to-model matrices from local pos/quat (parents precede children)."""
    world: list[Mat34] = []
    for b in bones:
        local = quat_to_mat34(b.quat, b.pos)
        world.append(local if b.parent < 0 else mat34_mul(world[b.parent], local))
    return world
