"""Reader for Source 1 optimized mesh data (.dx90.vtx / .dx80.vtx / .sw.vtx, version 7).

Newer branches (L4D2 and later, many GMod-era v49 models) append topology fields to the
strip-group and strip headers. The layout is detected by validating both variants.
"""

from __future__ import annotations

from dataclasses import dataclass

from .binary import FormatError, Reader

VTX_VERSION = 7
VTX_VERTEX_SIZE = 9


@dataclass
class StripGroup:
    flags: int
    vertex_ids: list[int]  # origMeshVertID per strip-group vertex
    triangles: list[tuple[int, int, int]]  # mesh-local vertex ids


@dataclass
class VtxMesh:
    flags: int
    strip_groups: list[StripGroup]

    def triangles(self) -> list[tuple[int, int, int]]:
        return [t for g in self.strip_groups for t in g.triangles]


@dataclass
class VtxLod:
    switch_point: float
    meshes: list[VtxMesh]


@dataclass
class VtxFile:
    checksum: int
    num_lods: int
    max_bones_per_vert: int
    layout: str  # "classic" or "extended"
    # body_parts[bp][model][lod]
    body_parts: list[list[list[VtxLod]]]


_LAYOUTS = {"classic": (25, 27), "extended": (33, 35)}


def read_vtx(data: bytes) -> VtxFile:
    r = Reader(data, "vtx")
    if len(data) < 36:
        raise FormatError("vtx: file too small")
    version, _cache, _mbs, _mbt, max_bones_vert, checksum, num_lods, _mrl, num_bp, bp_off = r.unpack(
        "iiHHiiiiii", 0
    )
    if version != VTX_VERSION:
        raise FormatError(f"vtx: version {version} is not supported (supported: 7)")
    errors = []
    for layout in ("classic", "extended"):
        try:
            parts = _read_parts(r, num_bp, bp_off, *_LAYOUTS[layout])
            return VtxFile(checksum, num_lods, max_bones_vert, layout, parts)
        except FormatError as exc:
            errors.append(f"{layout}: {exc}")
    raise FormatError("vtx: no known strip layout fits this file (" + "; ".join(errors) + ")")


def _read_parts(r: Reader, num_bp: int, bp_off: int, sg_size: int, strip_size: int):
    parts = []
    for b in range(num_bp):
        bo = bp_off + b * 8
        num_models, model_off = r.unpack("ii", bo)
        models = []
        for m in range(num_models):
            mo = bo + model_off + m * 8
            num_lods, lod_off = r.unpack("ii", mo)
            lods = []
            for lod in range(num_lods):
                lo = mo + lod_off + lod * 12
                num_meshes, mesh_off, switch = r.unpack("iif", lo)
                meshes = []
                for me in range(num_meshes):
                    meo = lo + mesh_off + me * 9
                    num_sg, sg_off = r.unpack("ii", meo)
                    mflags = r.u8(meo + 8)
                    groups = []
                    for g in range(num_sg):
                        go = meo + sg_off + g * sg_size
                        groups.append(_read_strip_group(r, go, strip_size))
                    meshes.append(VtxMesh(mflags, groups))
                lods.append(VtxLod(switch, meshes))
            models.append(lods)
        parts.append(models)
    return parts


def _read_strip_group(r: Reader, go: int, strip_size: int) -> StripGroup:
    num_verts, vert_off, num_idx, idx_off, num_strips, strip_off = r.unpack("6i", go)
    flags = r.u8(go + 24)
    if min(num_verts, num_idx, num_strips) < 0 or num_idx % 1:
        raise FormatError(f"strip group at {go} has negative counts")
    vids = [r.u16(go + vert_off + i * VTX_VERTEX_SIZE + 4) for i in range(num_verts)]
    indices = r.unpack(f"{num_idx}H", go + idx_off) if num_idx else ()
    tris: list[tuple[int, int, int]] = []
    for s in range(num_strips):
        so = go + strip_off + s * strip_size
        s_num_idx, s_idx_off, s_num_verts, s_vert_off = r.unpack("4i", so)
        s_flags = r.u8(so + 18)
        if s_idx_off < 0 or s_idx_off + s_num_idx > num_idx or s_vert_off + s_num_verts > num_verts:
            raise FormatError(f"strip at {so} references data outside its strip group")
        idx = indices[s_idx_off : s_idx_off + s_num_idx]
        for i in idx:
            if i >= num_verts:
                raise FormatError(f"strip at {so} index {i} exceeds {num_verts} vertices")
        if s_flags & 0x02:  # triangle strip
            for i in range(len(idx) - 2):
                a, b, c = idx[i], idx[i + 1], idx[i + 2]
                if i % 2:
                    a, b = b, a
                if a != b and b != c and a != c:
                    tris.append((vids[a], vids[b], vids[c]))
        else:
            if len(idx) % 3:
                raise FormatError(f"triangle list at {so} has {len(idx)} indices")
            for i in range(0, len(idx), 3):
                tris.append((vids[idx[i]], vids[idx[i + 1]], vids[idx[i + 2]]))
    return StripGroup(flags, vids, tris)
