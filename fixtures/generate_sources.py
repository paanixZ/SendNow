"""Write the hand-authored source files (QC/SMD/VMT/texture) for the SourceBridge fixtures.

These sources are our own work (MIT). `build.py` compiles them to real Source 1 files with an
independent compiler (mdlc). Keeping the generator makes every vertex reproducible.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

SRC = Path(__file__).parent / "src"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def png(path: Path, width: int, height: int, pixel) -> None:
    rows = b""
    for y in range(height):
        rows += b"\0" + b"".join(bytes(pixel(x, y)) for x in range(width))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def smd(nodes, frames, triangles) -> str:
    """nodes: [(id, name, parent)], frames: [[(id, pos, rot)]], triangles: [(mat, [(bone_links, p, n, uv)])]."""
    out = ["version 1", "nodes"]
    out += [f'{i} "{name}" {parent}' for i, name, parent in nodes]
    out += ["end", "skeleton"]
    for t, frame in enumerate(frames):
        out.append(f"time {t}")
        for i, p, r in frame:
            out.append(f"{i} {p[0]:.6f} {p[1]:.6f} {p[2]:.6f} {r[0]:.6f} {r[1]:.6f} {r[2]:.6f}")
    out.append("end")
    if triangles is not None:
        out.append("triangles")
        for mat, verts in triangles:
            out.append(mat)
            for links, p, n, uv in verts:
                parent = links[0][0]
                link_txt = f" {len(links)} " + " ".join(f"{b} {w:.6f}" for b, w in links)
                out.append(
                    f"{parent} {p[0]:.6f} {p[1]:.6f} {p[2]:.6f} {n[0]:.6f} {n[1]:.6f} {n[2]:.6f} "
                    f"{uv[0]:.6f} {uv[1]:.6f}{link_txt}"
                )
        out.append("end")
    return "\n".join(out) + "\n"


def box_triangles(mat, lo, hi, bone=0, uv_scale=1.0):
    """Axis aligned box, outward facing, counter-clockwise when seen from outside."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    faces = [
        ((0, 0, -1), [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)]),
        ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
        ((0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
        ((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
        ((0, 1, 0), [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)]),
        ((-1, 0, 0), [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)]),
    ]
    uvs = [(0, 0), (uv_scale, 0), (uv_scale, uv_scale), (0, uv_scale)]
    tris = []
    links = [(bone, 1.0)]
    for n, q in faces:
        for a, b, c in ((0, 1, 2), (0, 2, 3)):
            tris.append((mat, [(links, q[i], n, uvs[i]) for i in (a, b, c)]))
    return tris


def crate() -> None:
    d = SRC / "crate"
    nodes = [(0, "static_prop", -1)]
    frame = [[(0, (0, 0, 0), (0, 0, 0))]]
    lid = box_triangles("crate", (-14, -14, 32), (14, 14, 34))
    write(d / "crate_ref.smd", smd(nodes, frame, box_triangles("crate", (-16, -16, 0), (16, 16, 32)) + lid))
    write(d / "crate_lod1.smd", smd(nodes, frame, box_triangles("crate", (-16, -16, 0), (16, 16, 32))))
    write(d / "crate_phys.smd", smd(nodes, frame, box_triangles("crate", (-16, -16, 0), (16, 16, 32))))
    write(d / "crate_idle.smd", smd(nodes, frame, None))
    write(
        d / "crate.qc",
        """$modelname "sourcebridge/crate.mdl"
$staticprop
$body body "crate_ref.smd"
$lod 30
{
	replacemodel "crate_ref.smd" "crate_lod1.smd"
}
$cdmaterials "models/sourcebridge/"
$texturegroup skinfamilies
{
	{ "crate" }
	{ "crate_dark" }
}
$surfaceprop "wood_crate"
$keyvalues
{
	prop_data
	{
		"base" "Wooden.Medium"
	}
}
$sequence idle "crate_idle.smd"
$collisionmodel "crate_phys.smd" {
	$mass 40
}
""",
    )

    def wood(dark: bool):
        def pixel(x, y):
            plank = (y // 16) % 2
            grain = int(18 * math.sin(x * 0.35 + y * 0.05 + plank * 2.0))
            base = (150, 105, 60) if not dark else (80, 55, 35)
            edge = 40 if y % 16 in (0, 15) or x in (0, 63) else 0
            return tuple(max(0, min(255, c + grain - edge)) for c in base) + (255,)

        return pixel

    mats = d / "materials" / "models" / "sourcebridge"
    png(mats / "crate.png", 64, 64, wood(False))
    png(mats / "crate_dark.png", 64, 64, wood(True))
    for name in ("crate", "crate_dark"):
        write(
            mats / f"{name}.vmt",
            f""""VertexLitGeneric"
{{
	"$basetexture" "models/sourcebridge/{name}"
	"$surfaceprop" "Wood_Crate"
}}
""",
        )


# ---------------------------------------------------------------------------------- character

# (name, parent, local position, local rotation [RadianEuler x=roll, y=pitch, z=yaw])
MANNEQUIN_BONES = [
    ("ValveBiped.Bip01_Pelvis", -1, (0, 0, 38), (0, 0, 0)),
    ("ValveBiped.Bip01_Spine", 0, (0, 0, 4), (0, 0, 0)),
    ("ValveBiped.Bip01_Spine2", 1, (0, 0, 10), (0, 0, 0)),
    ("ValveBiped.Bip01_Neck1", 2, (0, 0, 10), (0, 0, 0)),
    ("ValveBiped.Bip01_Head1", 3, (0, 0, 4), (0, 0, 0)),
    # arms get a 90 degree rest yaw so their local X points along the arm (tests hierarchy math)
    ("ValveBiped.Bip01_L_UpperArm", 2, (0, 6, 8), (0, 0, math.pi / 2)),
    ("ValveBiped.Bip01_L_Forearm", 5, (11, 0, 0), (0, 0, 0)),
    ("ValveBiped.Bip01_L_Hand", 6, (10, 0, 0), (0, 0, 0)),
    ("ValveBiped.Bip01_R_UpperArm", 2, (0, -6, 8), (0, 0, -math.pi / 2)),
    ("ValveBiped.Bip01_R_Forearm", 8, (11, 0, 0), (0, 0, 0)),
    ("ValveBiped.Bip01_R_Hand", 9, (10, 0, 0), (0, 0, 0)),
    ("ValveBiped.Bip01_L_Thigh", 0, (0, 4, -2), (0, 0, 0)),
    ("ValveBiped.Bip01_L_Calf", 11, (0, 0, -17), (0, 0, 0)),
    ("ValveBiped.Bip01_L_Foot", 12, (0, 0, -17), (0, 0, 0)),
    ("ValveBiped.Bip01_R_Thigh", 0, (0, -4, -2), (0, 0, 0)),
    ("ValveBiped.Bip01_R_Calf", 14, (0, 0, -17), (0, 0, 0)),
    ("ValveBiped.Bip01_R_Foot", 15, (0, 0, -17), (0, 0, 0)),
]
BONE_INDEX = {b[0]: i for i, b in enumerate(MANNEQUIN_BONES)}


def _quat(rot):
    sr, cr = math.sin(rot[0] / 2), math.cos(rot[0] / 2)
    sp, cp = math.sin(rot[1] / 2), math.cos(rot[1] / 2)
    sy, cy = math.sin(rot[2] / 2), math.cos(rot[2] / 2)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def _mat(q, p):
    x, y, z, w = q
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), p[0]],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), p[1]],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), p[2]],
    ]


def _mul(a, b):
    out = []
    for r in range(3):
        row = [sum(a[r][k] * b[k][c] for k in range(3)) for c in range(4)]
        row[3] += a[r][3]
        out.append(row)
    return out


def _apply(m, p):
    return tuple(m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3] for r in range(3))


def _rotate(m, v):
    return tuple(m[r][0] * v[0] + m[r][1] * v[1] + m[r][2] * v[2] for r in range(3))


def bind_world():
    world = []
    for _name, parent, pos, rot in MANNEQUIN_BONES:
        local = _mat(_quat(rot), pos)
        world.append(local if parent < 0 else _mul(world[parent], local))
    return world


def _limb_box(mat, bone, child_bone, lo, hi, world, blend_end=None):
    """Box in the bone's local frame; vertices at the blend_end face are shared 50/50 with child_bone."""
    tris = box_triangles(mat, lo, hi, bone)
    out = []
    for m, verts in tris:
        nv = []
        for links, p, n, uv in verts:
            links = [(bone, 1.0)]
            if child_bone is not None and blend_end is not None:
                axis, value = blend_end
                if abs(p[axis] - value) < 1e-6:
                    links = [(bone, 0.5), (child_bone, 0.5)]
            nv.append((links, _apply(world[bone], p), _rotate(world[bone], n), uv))
        out.append((m, nv))
    return out


def mannequin_mesh(detail: int = 1):
    """detail=1 reference mesh, detail=0 simplified LOD (no hands/feet)."""
    w = bind_world()
    B = BONE_INDEX
    body = []
    body += _limb_box(
        "mannequin_skin",
        B["ValveBiped.Bip01_Pelvis"],
        B["ValveBiped.Bip01_Spine"],
        (-4, -6, -3),
        (4, 6, 4),
        w,
        (2, 4),
    )
    body += _limb_box(
        "mannequin_skin",
        B["ValveBiped.Bip01_Spine"],
        B["ValveBiped.Bip01_Spine2"],
        (-4, -6, 0),
        (4, 6, 10),
        w,
        (2, 10),
    )
    body += _limb_box(
        "mannequin_skin",
        B["ValveBiped.Bip01_Spine2"],
        B["ValveBiped.Bip01_Neck1"],
        (-4, -7, 0),
        (4, 7, 10),
        w,
        (2, 10),
    )
    body += _limb_box("mannequin_skin", B["ValveBiped.Bip01_Neck1"], None, (-2, -2, 0), (2, 2, 4), w)
    for side in ("L", "R"):
        ua, fa, hand = (B[f"ValveBiped.Bip01_{side}_{n}"] for n in ("UpperArm", "Forearm", "Hand"))
        body += _limb_box("mannequin_skin", ua, fa, (0, -2, -2), (11, 2, 2), w, (0, 11))
        body += _limb_box("mannequin_skin", fa, hand, (0, -1.5, -1.5), (10, 1.5, 1.5), w, (0, 10))
        if detail:
            body += _limb_box("mannequin_skin", hand, None, (0, -2, -1), (4, 2, 1), w)
        th, ca, ft = (B[f"ValveBiped.Bip01_{side}_{n}"] for n in ("Thigh", "Calf", "Foot"))
        body += _limb_box("mannequin_skin", th, ca, (-2.5, -2.5, -17), (2.5, 2.5, 0), w, (2, -17))
        body += _limb_box("mannequin_skin", ca, ft, (-2, -2, -17), (2, 2, 0), w, (2, -17))
        if detail:
            body += _limb_box("mannequin_skin", ft, None, (-2, -2, -3), (6, 2, 0), w)
    head = _limb_box("mannequin_skin", B["ValveBiped.Bip01_Head1"], None, (-4, -4, 0), (4, 4, 9), w)
    helmet = _limb_box("mannequin_helmet", B["ValveBiped.Bip01_Head1"], None, (-5, -5, -1), (5, 5, 10), w)
    return body, head, helmet


def _anim_frames(kind: str, count: int):
    frames = []
    for f in range(count):
        t = f / count * 2 * math.pi
        frame = []
        for i, (name, _parent, pos, rot) in enumerate(MANNEQUIN_BONES):
            r = list(rot)
            p = list(pos)
            if kind == "idle":
                if name.endswith("Spine2"):
                    r[0] += 0.05 * math.sin(t)
                if name.endswith("Head1"):
                    r[2] += 0.2 * math.sin(t)
                if name.endswith("Pelvis"):
                    p[2] += 0.5 * math.sin(t)
            elif kind == "walk":
                swing = 0.5 * math.sin(t)
                if name.endswith("L_Thigh"):
                    r[1] += swing
                if name.endswith("R_Thigh"):
                    r[1] -= swing
                if name.endswith("L_Calf"):
                    r[1] += max(0.0, -0.8 * math.sin(t))
                if name.endswith("R_Calf"):
                    r[1] += max(0.0, 0.8 * math.sin(t))
                if name.endswith("L_UpperArm"):
                    r[1] -= 0.4 * math.sin(t)
                if name.endswith("R_UpperArm"):
                    r[1] -= 0.4 * math.sin(t)
                if name.endswith("Pelvis"):
                    p[2] += 0.8 * abs(math.sin(t))
            frame.append((i, tuple(p), tuple(r)))
        frames.append(frame)
    return frames


def mannequin() -> None:
    d = SRC / "mannequin"
    nodes = [(i, n, p) for i, (n, p, _pos, _rot) in enumerate(MANNEQUIN_BONES)]
    rest = [[(i, pos, rot) for i, (_n, _p, pos, rot) in enumerate(MANNEQUIN_BONES)]]
    body, head, helmet = mannequin_mesh(1)
    write(d / "mannequin_ref.smd", smd(nodes, rest, body))
    write(d / "mannequin_head.smd", smd(nodes, rest, head))
    write(d / "mannequin_helmet.smd", smd(nodes, rest, helmet))
    write(d / "mannequin_idle.smd", smd(nodes, _anim_frames("idle", 20), None))
    write(d / "mannequin_walk.smd", smd(nodes, _anim_frames("walk", 30), None))

    # ragdoll: one convex box per major bone, authored in model space and skinned 100% to that bone
    w = bind_world()
    B = BONE_INDEX
    phys = []
    pieces = [
        ("ValveBiped.Bip01_Pelvis", (-4, -6, -3), (4, 6, 4)),
        ("ValveBiped.Bip01_Spine2", (-4, -7, 0), (4, 7, 10)),
        ("ValveBiped.Bip01_Head1", (-4, -4, 0), (4, 4, 9)),
        ("ValveBiped.Bip01_L_UpperArm", (0, -2, -2), (11, 2, 2)),
        ("ValveBiped.Bip01_L_Forearm", (0, -1.5, -1.5), (14, 1.5, 1.5)),
        ("ValveBiped.Bip01_R_UpperArm", (0, -2, -2), (11, 2, 2)),
        ("ValveBiped.Bip01_R_Forearm", (0, -1.5, -1.5), (14, 1.5, 1.5)),
        ("ValveBiped.Bip01_L_Thigh", (-2.5, -2.5, -17), (2.5, 2.5, 0)),
        ("ValveBiped.Bip01_L_Calf", (-2, -2, -20), (6, 2, 0)),
        ("ValveBiped.Bip01_R_Thigh", (-2.5, -2.5, -17), (2.5, 2.5, 0)),
        ("ValveBiped.Bip01_R_Calf", (-2, -2, -20), (6, 2, 0)),
    ]
    for name, lo, hi in pieces:
        phys += _limb_box("mannequin_skin", B[name], None, lo, hi, w)
    write(d / "mannequin_phys.smd", smd(nodes, rest, phys))

    constraints = "\n".join(
        f'\t$jointconstrain "{n}" {axis} limit {lo} {hi} 0'
        for n, lims in [
            ("ValveBiped.Bip01_Head1", {"x": (-20, 20), "y": (-30, 30), "z": (-40, 40)}),
            ("ValveBiped.Bip01_L_Forearm", {"x": (0, 0), "y": (-120, 0), "z": (0, 0)}),
            ("ValveBiped.Bip01_R_Forearm", {"x": (0, 0), "y": (-120, 0), "z": (0, 0)}),
            ("ValveBiped.Bip01_L_Calf", {"x": (0, 0), "y": (0, 140), "z": (0, 0)}),
            ("ValveBiped.Bip01_R_Calf", {"x": (0, 0), "y": (0, 140), "z": (0, 0)}),
        ]
        for axis, (lo, hi) in lims.items()
    )
    write(
        d / "mannequin.qc",
        f"""$modelname "sourcebridge/mannequin.mdl"
$body body "mannequin_ref.smd"
$bodygroup head
{{
	studio "mannequin_head.smd"
	studio "mannequin_helmet.smd"
}}
$cdmaterials "models/sourcebridge/"
$surfaceprop "flesh"
$attachment "eyes" "ValveBiped.Bip01_Head1" 5.00 0.00 5.00 rotate 0 0 0
$attachment "anim_attachment_RH" "ValveBiped.Bip01_R_Hand" 3.00 0.00 0.00 rotate 0 0 0
$hboxset "default"
$hbox 1 "ValveBiped.Bip01_Head1" -4 -4 0 4 4 9
$hbox 2 "ValveBiped.Bip01_Spine2" -4 -7 0 4 7 10
$hbox 3 "ValveBiped.Bip01_Pelvis" -4 -6 -3 4 6 4
$hbox 6 "ValveBiped.Bip01_L_Thigh" -2.5 -2.5 -17 2.5 2.5 0
$hbox 7 "ValveBiped.Bip01_R_Thigh" -2.5 -2.5 -17 2.5 2.5 0
$sequence idle "mannequin_idle.smd" loop fps 30 activity ACT_IDLE 1
$sequence walk "mannequin_walk.smd" loop fps 30 activity ACT_WALK 1
$collisionjoints "mannequin_phys.smd" {{
	$mass 70
	$rootbone "ValveBiped.Bip01_Pelvis"
{constraints}
}}
""",
    )

    def skin(x, y):
        return (200, 170, 140, 255) if (x // 8 + y // 8) % 2 else (185, 155, 125, 255)

    def visor(x, y):
        # opaque shell with a transparent slit: exercises $alphatest
        return (60, 60, 70, 0 if 24 <= y < 32 else 255)

    mats = d / "materials" / "models" / "sourcebridge"
    png(mats / "mannequin_skin.png", 64, 64, skin)
    png(mats / "mannequin_helmet.png", 64, 64, visor)
    write(
        mats / "mannequin_skin.vmt",
        '"VertexLitGeneric"\n{\n\t"$basetexture" "models/sourcebridge/mannequin_skin"\n\t"$surfaceprop" "Flesh"\n}\n',
    )
    write(
        mats / "mannequin_helmet.vmt",
        '"VertexLitGeneric"\n{\n\t"$basetexture" "models/sourcebridge/mannequin_helmet"\n'
        '\t"$alphatest" "1"\n\t"$alphatestreference" "0.5"\n\t"$nocull" "1"\n\t"$envmap" "env_cubemap"\n}\n',
    )


if __name__ == "__main__":
    import gen_vehicle

    crate()
    mannequin()
    gen_vehicle.write_sources(SRC, write, smd, box_triangles, png)
    print(f"sources written to {SRC}")
