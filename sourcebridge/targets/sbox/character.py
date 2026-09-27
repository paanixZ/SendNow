"""Skeleton-related ModelDoc output: animations, attachments, hitboxes, ragdoll joints.

All node classes and keys come from Facepunch's shipped ModelDoc files
(templates/sbox/reference/modeldoc_classes.json). Where s&box has no equivalent of a Source 1
feature, the closest node is used and the journal says "approximated".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ...formats.anim import DecodedAnimation, decode_animation
from ...formats.binary import FormatError
from ...formats.mdl import StudioModel
from ...journal import Journal
from ...transform import (
    bone_world_matrices,
    mat34_apply,
    mat34_inverse,
    mat34_mul,
    mat34_to_qangle_deg,
    pose_world,
    quat_to_radian_euler,
)

# Source 1 hit groups (shareddefs.h HITGROUP_*) -> descriptive tags
HITGROUP_TAGS = {0: "generic", 1: "head", 2: "chest", 3: "stomach", 4: "arm left", 5: "arm right",
                 6: "leg left", 7: "leg right", 10: "gear"}  # fmt: skip


@dataclass
class SequenceCheck:
    """Expected model-space bone positions at a frame; used by the in-engine target test."""

    sequence: str
    frame: int
    time: float
    bones: dict[str, tuple[float, float, float]]


@dataclass
class CharacterResult:
    nodes: list[dict] = field(default_factory=list)
    animations: dict[str, DecodedAnimation] = field(default_factory=dict)
    checks: list[SequenceCheck] = field(default_factory=list)
    sequences: list[dict] = field(default_factory=list)


def _f(x: float) -> str:
    s = f"{x:.6f}"
    return "0.000000" if s == "-0.000000" else s


def write_smd_animation(mdl: StudioModel, anim: DecodedAnimation) -> str:
    out = ["version 1", "nodes"]
    for b in mdl.bones:
        out.append(f'{b.index} "{b.name}" {b.parent}')
    out += ["end", "skeleton"]
    for t, frame in enumerate(anim.frames):
        out.append(f"time {t}")
        for bi, (p, q) in enumerate(frame):
            r = quat_to_radian_euler(q)
            out.append(f"{bi} {_f(p[0])} {_f(p[1])} {_f(p[2])} {_f(r[0])} {_f(r[1])} {_f(r[2])}")
    out.append("end")
    return "\n".join(out) + "\n"


def _end_bones(mdl: StudioModel, limit: int = 6) -> list[int]:
    """Leaf bones (hands, feet, head): their positions depend on every rotation up the chain."""
    has_child = {b.parent for b in mdl.bones}
    leaves = [b.index for b in mdl.bones if b.index not in has_child]
    return leaves[:limit]


def build_animations(
    mdl: StudioModel,
    mdl_data: bytes,
    ani_data: bytes | None,
    model_dir: str,
    name: str,
    out,
    journal: Journal,
    subj: str,
) -> CharacterResult:
    res = CharacterResult()
    decoded: dict[int, DecodedAnimation] = {}
    for desc in mdl.anim_descs:
        try:
            decoded[desc.index] = decode_animation(mdl, mdl_data, desc, ani_data)
        except FormatError as exc:
            journal.error(subj, f"animation {desc.name}", str(exc))
    anim_nodes = []
    leaves = _end_bones(mdl)
    for seq in mdl.sequences:
        if not seq.anim_indices:
            journal.lost(subj, f"sequence {seq.label}", "has no animation")
            continue
        if seq.group_size[0] * seq.group_size[1] > 1:
            journal.lost(
                subj,
                f"sequence {seq.label}",
                f"blend sequence ({seq.group_size[0]}x{seq.group_size[1]}); only the first animation is exported",
            )
        anim = decoded.get(seq.anim_indices[0])
        if anim is None:
            continue
        smd_name = f"{name}_anim_{_safe(seq.label)}"
        rel = f"{model_dir}/{smd_name}.smd"
        out.add(rel, write_smd_animation(mdl, anim), "animation")
        looping = bool(seq.flags & 0x1)
        delta = anim.delta
        anim_nodes.append(
            {
                "_class": "AnimFile",
                "name": seq.label,
                "activity_name": seq.activity,
                "activity_weight": seq.activity_weight or 1,
                "weight_list_name": "",
                "fade_in_time": float(seq.fade_in),
                "fade_out_time": float(seq.fade_out),
                "looping": looping,
                "delta": delta,
                "worldSpace": False,
                "hidden": bool(seq.flags & 0x400),
                "anim_markup_ordered": False,
                "disable_compression": False,
                "disable_interpolation": False,
                "enable_scale": False,
                "source_filename": rel,
                "start_frame": -1,
                "end_frame": -1,
                "framerate": float(anim.fps),
                "take": 0,
                "reverse": False,
            }
        )
        journal.converted(
            subj,
            f"sequence {seq.label}",
            f"{len(anim.frames)} frames @ {anim.fps:g} fps decoded to animation SMD "
            f"(looping={looping}, activity={seq.activity or '-'})",
        )
        if seq.num_events:
            journal.lost(
                subj, f"sequence {seq.label} events", f"{seq.num_events} animation events not mapped yet"
            )
        res.sequences.append(
            {
                "name": seq.label,
                "frames": len(anim.frames),
                "fps": anim.fps,
                "looping": looping,
                "activity": seq.activity,
            }
        )
        n = len(anim.frames)
        for f in sorted({0, n // 3, (2 * n) // 3}):
            world = pose_world(mdl.bones, anim.frames[f])
            res.checks.append(
                SequenceCheck(
                    seq.label,
                    f,
                    f / anim.fps if anim.fps else 0.0,
                    {
                        mdl.bones[b].name: tuple(
                            round(v, 4) for v in (world[b][3], world[b][7], world[b][11])
                        )
                        for b in leaves
                    },
                )
            )
    if anim_nodes:
        res.nodes.append({"_class": "AnimationList", "children": anim_nodes, "default_root_bone_name": ""})
    res.animations = {mdl.anim_descs[i].name: a for i, a in decoded.items()}
    return res


def attachment_nodes(mdl: StudioModel, journal: Journal, subj: str) -> list[dict]:
    if not mdl.attachments:
        return []
    items = []
    for a in mdl.attachments:
        m = a.local
        pitch, yaw, roll = mat34_to_qangle_deg(m)
        items.append(
            {
                "_class": "Attachment",
                "name": a.name,
                "parent_bone": mdl.bones[a.bone].name if 0 <= a.bone < len(mdl.bones) else "",
                "relative_origin": [m[3], m[7], m[11]],
                "relative_angles": [pitch, yaw, roll],
                "weight": 1.0,
                "ignore_rotation": False,
            }
        )
    journal.converted(subj, "attachments", f"{len(items)} attachments (bone-relative origin and angles)")
    return [{"_class": "AttachmentList", "children": items}]


def hitbox_nodes(mdl: StudioModel, journal: Journal, subj: str) -> list[dict]:
    if not mdl.hitbox_sets or not any(s.hitboxes for s in mdl.hitbox_sets):
        return []
    sets = []
    for hs in mdl.hitbox_sets:
        boxes = []
        for i, h in enumerate(hs.hitboxes):
            lo, hi = h.bbmin, h.bbmax
            ext = [hi[k] - lo[k] for k in range(3)]
            axis = max(range(3), key=lambda k: ext[k])
            others = [k for k in range(3) if k != axis]
            radius = max(ext[k] for k in others) / 2.0
            center = [(lo[k] + hi[k]) / 2.0 for k in range(3)]
            half = max(0.0, ext[axis] / 2.0 - radius)
            p0 = list(center)
            p1 = list(center)
            p0[axis] -= half
            p1[axis] += half
            bone = mdl.bones[h.bone].name if 0 <= h.bone < len(mdl.bones) else ""
            boxes.append(
                {
                    "_class": "HitboxCapsule",
                    "name": h.name or f"hitbox_{i}_{_safe(bone)}",
                    "parent_bone": bone,
                    "surface_property": mdl.bones[h.bone].surface_prop or mdl.surface_prop or "default",
                    "translation_only": False,
                    "tags": HITGROUP_TAGS.get(h.group, f"group{h.group}"),
                    "radius": radius,
                    "point0": p0,
                    "point1": p1,
                }
            )
        sets.append({"_class": "HitboxSet", "name": hs.name or "default", "children": boxes})
    total = sum(len(s["children"]) for s in sets)
    journal.approximated(
        subj,
        "hitboxes",
        f"{total} Source 1 box hitboxes as enclosing HitboxCapsules (s&box has no box hitbox); "
        "hit groups kept as tags",
    )
    return [{"_class": "HitboxSetList", "children": sets}]


def joint_nodes(mdl: StudioModel, phy, journal: Journal, subj: str) -> list[dict]:
    """Ragdoll constraints (.phy text) -> PhysicsJointConical / PhysicsJointRevolute."""
    constraints = [b for b in phy.blocks if b.kind == "ragdollconstraint"]
    if not constraints:
        return []
    solid_bone: dict[int, str] = {}
    for b in phy.blocks:
        if b.kind == "solid" and "index" in b.values:
            solid_bone[int(b.values["index"])] = b.values.get("name", "")
    bind = bone_world_matrices(mdl.bones)
    by_name = {b.name.lower(): b.index for b in mdl.bones}
    joints = []
    for c in constraints:
        v = c.values
        parent = solid_bone.get(int(v.get("parent", -1)), "")
        child = solid_bone.get(int(v.get("child", -1)), "")
        if not parent or not child:
            journal.error(subj, "ragdoll constraint", f"refers to unknown solid(s): {v}")
            continue
        pi, ci = by_name.get(parent.lower()), by_name.get(child.lower())
        if pi is None or ci is None:
            journal.error(subj, "ragdoll constraint", f"bones {parent}/{child} not in skeleton")
            continue
        rel = mat34_mul(mat34_inverse(bind[pi]), bind[ci])  # child frame in parent body space
        pitch, yaw, roll = mat34_to_qangle_deg(rel)
        lim = {ax: (float(v.get(f"{ax}min", 0)), float(v.get(f"{ax}max", 0))) for ax in "xyz"}
        free = [ax for ax, (lo, hi) in lim.items() if hi - lo > 1e-3]
        friction = max(float(v.get(f"{ax}friction", 0)) for ax in "xyz")
        base = {
            "parent_body": parent,
            "child_body": child,
            "anchor_origin": [rel[3], rel[7], rel[11]],
            "anchor_angles": [pitch, yaw, roll],
            "collision_enabled": False,
            "linear_strength": 0.0,
            "angular_strength": 0.0,
            "friction": friction,
        }
        if len(free) == 1:
            lo, hi = lim[free[0]]
            joints.append(
                {
                    "_class": "PhysicsJointRevolute",
                    **base,
                    "enable_limit": True,
                    "min_angle": lo,
                    "max_angle": hi,
                }
            )
        else:
            swing = max([max(abs(lim[a][0]), abs(lim[a][1])) for a in "yz"] + [0.0])
            tlo, thi = lim["x"]
            joints.append(
                {
                    "_class": "PhysicsJointConical",
                    **base,
                    "enable_swing_limit": True,
                    "swing_limit": swing,
                    "swing_offset_angle": [0.0, 0.0, 0.0],
                    "enable_twist_limit": True,
                    "min_twist_angle": tlo,
                    "max_twist_angle": thi,
                }
            )
    journal.approximated(
        subj,
        "ragdoll constraints",
        f"{len(joints)} constraints: one free axis -> PhysicsJointRevolute, otherwise PhysicsJointConical "
        "(swing = largest y/z limit, twist = x limits); anchor at the child bone",
    )
    return [{"_class": "PhysicsJointList", "children": joints}] if joints else []


def _safe(s: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_]+", "_", s).strip("_").lower() or "x"


def bind_leaf_positions(mdl: StudioModel) -> dict[str, tuple[float, float, float]]:
    w = bone_world_matrices(mdl.bones)
    return {mdl.bones[b].name: mat34_apply(w[b], (0.0, 0.0, 0.0)) for b in _end_bones(mdl)}


def angle_between(a, b) -> float:
    dot = abs(sum(x * y for x, y in zip(a, b, strict=True)))
    return 2 * math.acos(min(1.0, dot))
