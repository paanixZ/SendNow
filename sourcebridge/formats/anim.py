"""Decode Source 1 bone animation data (mstudioanim_t chains) into per-frame local bone poses.

Follows the public studio.h layouts and the sampling rules of the Source SDK's bone setup
(ExtractAnimValue / CalcBoneQuaternion / CalcBonePosition): compressed rotations are either
raw Quaternion48/64 or run-length encoded Euler values scaled by the bone's rotscale and added
to the bone's rest rotation (unless the animation is a delta); positions likewise.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from ..transform import euler_to_quat
from .binary import FormatError, Reader
from .mdl import AnimDesc, Bone, StudioModel

ANIM_RAWPOS = 0x01
ANIM_RAWROT = 0x02
ANIM_ANIMPOS = 0x04
ANIM_ANIMROT = 0x08
ANIM_DELTA = 0x10
ANIM_RAWROT2 = 0x20

STUDIO_LOOPING = 0x0001
STUDIO_DELTA = 0x0004
STUDIO_ALLZEROS = 0x0020

Pose = tuple[tuple[float, float, float], tuple[float, float, float, float]]  # (pos, quat xyzw)


@dataclass
class DecodedAnimation:
    name: str
    fps: float
    looping: bool
    delta: bool
    frames: list[list[Pose]]  # frames[f][bone]
    animated_bones: set[int]


def _quat48(r: Reader, o: int) -> tuple[float, float, float, float]:
    x, y, zw = r.unpack("HHH", o)
    z = zw & 0x7FFF
    wneg = zw >> 15
    qx = (x - 32768) * (1 / 32768.0)
    qy = (y - 32768) * (1 / 32768.0)
    qz = (z - 16384) * (1 / 16384.0)
    w = math.sqrt(max(0.0, 1 - qx * qx - qy * qy - qz * qz))
    return (qx, qy, qz, -w if wneg else w)


def _quat64(r: Reader, o: int) -> tuple[float, float, float, float]:
    (v,) = r.unpack("Q", o)
    x = v & 0x1FFFFF
    y = (v >> 21) & 0x1FFFFF
    z = (v >> 42) & 0x1FFFFF
    wneg = v >> 63
    qx = (x - 1048576) * (1 / 1048576.5)
    qy = (y - 1048576) * (1 / 1048576.5)
    qz = (z - 1048576) * (1 / 1048576.5)
    w = math.sqrt(max(0.0, 1 - qx * qx - qy * qy - qz * qz))
    return (qx, qy, qz, -w if wneg else w)


def _vec48(r: Reader, o: int) -> tuple[float, float, float]:
    return struct.unpack_from("<3e", r.raw(o, 6))


def _extract(r: Reader, base: int, frame: int, scale: float) -> float:
    """ExtractAnimValue: walk run-length encoded shorts."""
    k = frame
    o = base
    for _ in range(100_000):
        valid, total = r.u8(o), r.u8(o + 1)
        if total == 0:
            return 0.0
        if total > k:
            if valid > k:
                return r.i16(o + 2 * (k + 1)) * scale
            return r.i16(o + 2 * valid) * scale
        k -= total
        o += 2 * (valid + 1)
    raise FormatError(f"anim: run-length data at {base} does not terminate")


def _valueptr(r: Reader, o: int) -> tuple[int, int, int]:
    offs = r.unpack("3h", o)
    return tuple(o + x if x > 0 else 0 for x in offs)


def _sample_chain(
    r: Reader, start: int, frame: int, bones: list[Bone], delta: bool, out: list[Pose], seen: set[int]
):
    o = start
    for _ in range(len(bones) + 1):
        bone_i, flags, next_off = r.unpack("BBh", o)
        if bone_i >= len(bones):
            raise FormatError(f"anim: bone index {bone_i} out of range at {o}")
        b = bones[bone_i]
        d = delta or bool(flags & ANIM_DELTA)
        # Payload is written sequentially by studiomdl: raw rotation, raw position, rotation
        # value pointers, position value pointers (the order Crowbar reads as well).
        cur = o + 4
        raw_q = raw_p = rot_v = pos_v = None
        if flags & ANIM_RAWROT:
            raw_q = _quat48(r, cur)
            cur += 6
        if flags & ANIM_RAWROT2:
            raw_q = _quat64(r, cur)
            cur += 8
        if flags & ANIM_RAWPOS:
            raw_p = _vec48(r, cur)
            cur += 6
        if flags & ANIM_ANIMROT:
            rot_v = _valueptr(r, cur)
            cur += 6
        if flags & ANIM_ANIMPOS:
            pos_v = _valueptr(r, cur)
            cur += 6
        # rotation
        if raw_q is not None:
            q = raw_q
        elif rot_v is not None:
            ang = [(_extract(r, ptr, frame, b.rot_scale[i]) if ptr else 0.0) for i, ptr in enumerate(rot_v)]
            if not d:
                ang = [ang[i] + b.rot[i] for i in range(3)]
            q = euler_to_quat(tuple(ang))
        else:
            q = (0.0, 0.0, 0.0, 1.0) if d else b.quat
        # position
        if raw_p is not None:
            p = raw_p
        elif pos_v is not None:
            p = [(_extract(r, ptr, frame, b.pos_scale[i]) if ptr else 0.0) for i, ptr in enumerate(pos_v)]
            if not d:
                p = [p[i] + b.pos[i] for i in range(3)]
            p = tuple(p)
        else:
            p = (0.0, 0.0, 0.0) if d else b.pos
        out[bone_i] = (tuple(p), q)
        seen.add(bone_i)
        if next_off == 0:
            return
        o += next_off
    raise FormatError("anim: bone chain longer than the skeleton")


def decode_animation(
    mdl: StudioModel, mdl_data: bytes, desc: AnimDesc, ani_data: bytes | None = None
) -> DecodedAnimation:
    """Sample every frame of one animation. `ani_data` is the external .ani file, if any."""
    delta = bool(desc.flags & STUDIO_DELTA)
    rest: list[Pose] = [
        ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)) if delta else (b.pos, b.quat) for b in mdl.bones
    ]
    frames: list[list[Pose]] = []
    seen: set[int] = set()
    rm = Reader(mdl_data, "mdl")
    ra = Reader(ani_data, "ani") if ani_data is not None else None
    for f in range(max(1, desc.num_frames)):
        pose = list(rest)
        if not desc.flags & STUDIO_ALLZEROS:
            block, index, frame = desc.anim_block, desc.anim_index, f
            if desc.section_frames:
                if desc.num_frames > desc.section_frames and f == desc.num_frames - 1:
                    frame = 0
                    section = (desc.num_frames - 1) // desc.section_frames + 1
                else:
                    section = f // desc.section_frames
                    frame = f - section * desc.section_frames
                block, index = rm.unpack("ii", desc.desc_offset + desc.section_index + section * 8)
            if block == 0:
                _sample_chain(rm, desc.desc_offset + index, frame, mdl.bones, delta, pose, seen)
            else:
                if ra is None:
                    raise FormatError(
                        f"anim {desc.name}: data is in animation block {block}, but no .ani file was given"
                    )
                if block >= len(mdl.anim_blocks):
                    raise FormatError(f"anim {desc.name}: animation block {block} out of range")
                data_start, _end = mdl.anim_blocks[block]
                _sample_chain(ra, data_start + index, frame, mdl.bones, delta, pose, seen)
        frames.append(pose)
    return DecodedAnimation(desc.name, desc.fps, bool(desc.flags & STUDIO_LOOPING), delta, frames, seen)
