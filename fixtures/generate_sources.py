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
    write(d / "crate_ref.smd", smd(nodes, frame, box_triangles("crate", (-16, -16, 0), (16, 16, 32))))
    write(d / "crate_phys.smd", smd(nodes, frame, box_triangles("crate", (-16, -16, 0), (16, 16, 32))))
    write(d / "crate_idle.smd", smd(nodes, frame, None))
    write(
        d / "crate.qc",
        """$modelname "sourcebridge/crate.mdl"
$staticprop
$body body "crate_ref.smd"
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


if __name__ == "__main__":
    crate()
    print(f"sources written to {SRC}")
