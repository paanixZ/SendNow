"""Rebuild triangle meshes from .mdl + .vvd + .vtx."""

from __future__ import annotations

from dataclasses import dataclass

from .formats.binary import FormatError
from .formats.mdl import StudioModel
from .formats.vtx import VtxFile
from .formats.vvd import Vertex, VertexFile


@dataclass
class MeshGroup:
    material_index: int  # index into mdl.textures (skin family 0 remapping applied by caller)
    triangles: list[tuple[int, int, int]]  # indices into ModelGeometry.vertices


@dataclass
class ModelGeometry:
    body_part: str
    body_part_index: int
    model_name: str
    model_index: int
    lod: int
    vertices: list[Vertex]
    meshes: list[MeshGroup]

    @property
    def triangle_count(self) -> int:
        return sum(len(m.triangles) for m in self.meshes)

    def bounds(self) -> tuple[tuple[float, ...], tuple[float, ...]] | None:
        used = {i for m in self.meshes for t in m.triangles for i in t}
        if not used:
            return None
        pts = [self.vertices[i].position for i in used]
        return tuple(min(p[k] for p in pts) for k in range(3)), tuple(
            max(p[k] for p in pts) for k in range(3)
        )


def extract(mdl: StudioModel, vvd: VertexFile, vtx: VtxFile, lod: int = 0) -> list[ModelGeometry]:
    if len(vtx.body_parts) != len(mdl.body_parts):
        raise FormatError(f"vtx has {len(vtx.body_parts)} body parts but mdl has {len(mdl.body_parts)}")
    all_verts = vvd.vertices_for_lod(lod)
    out = []
    for bpi, bp in enumerate(mdl.body_parts):
        vbp = vtx.body_parts[bpi]
        if len(vbp) != len(bp.models):
            raise FormatError(f"body part {bp.name}: vtx/mdl model count mismatch")
        for mi, sub in enumerate(bp.models):
            lods = vbp[mi]
            if not lods or sub.num_vertices == 0:
                out.append(ModelGeometry(bp.name, bpi, sub.name, mi, lod, [], []))
                continue
            if lod >= len(lods):
                continue
            vlod = lods[lod]
            if len(vlod.meshes) != len(sub.meshes):
                raise FormatError(f"model {sub.name}: vtx/mdl mesh count mismatch")
            base = sub.vertex_index // 48
            local: dict[int, int] = {}
            verts: list[Vertex] = []
            groups = []
            for me_i, me in enumerate(sub.meshes):
                tris = []
                for a, b, c in vlod.meshes[me_i].triangles():
                    idx = []
                    for mv in (a, b, c):
                        g = base + me.vertex_offset + mv
                        if g >= len(all_verts):
                            raise FormatError(f"model {sub.name}: vertex {g} beyond {len(all_verts)}")
                        if g not in local:
                            local[g] = len(verts)
                            verts.append(all_verts[g])
                        idx.append(local[g])
                    tris.append((idx[0], idx[1], idx[2]))
                groups.append(MeshGroup(me.material, tris))
            out.append(ModelGeometry(bp.name, bpi, sub.name, mi, lod, verts, groups))
    return out
