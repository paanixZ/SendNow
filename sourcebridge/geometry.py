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
    error: str | None = None  # set when the source data for this model is inconsistent

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
            if sub.num_vertices == 0:
                out.append(ModelGeometry(bp.name, bpi, sub.name, mi, lod, [], []))
                continue
            if not lods:
                out.append(
                    ModelGeometry(
                        bp.name,
                        bpi,
                        sub.name,
                        mi,
                        lod,
                        [],
                        [],
                        error=f"{sub.num_vertices} vertices in the MDL but no LOD data in the VTX",
                    )
                )
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


def bake_pose(geo: ModelGeometry, bind_world, pose_world) -> ModelGeometry:
    """Linear-blend skin a model into another pose; returns a new geometry in that pose."""
    from .transform import mat34_apply, mat34_inverse, mat34_mul

    skin = [mat34_mul(p, mat34_inverse(b)) for b, p in zip(bind_world, pose_world, strict=True)]
    verts = []
    for v in geo.vertices:
        pos = [0.0, 0.0, 0.0]
        nrm = [0.0, 0.0, 0.0]
        for b, w in zip(v.bones, v.weights, strict=True):
            m = skin[b]
            p = mat34_apply(m, v.position)
            n = (
                m[0] * v.normal[0] + m[1] * v.normal[1] + m[2] * v.normal[2],
                m[4] * v.normal[0] + m[5] * v.normal[1] + m[6] * v.normal[2],
                m[8] * v.normal[0] + m[9] * v.normal[1] + m[10] * v.normal[2],
            )
            for k in range(3):
                pos[k] += w * p[k]
                nrm[k] += w * n[k]
        ln = sum(x * x for x in nrm) ** 0.5 or 1.0
        verts.append(Vertex(v.weights, v.bones, tuple(pos), tuple(x / ln for x in nrm), v.uv))
    return ModelGeometry(
        geo.body_part,
        geo.body_part_index,
        geo.model_name,
        geo.model_index,
        geo.lod,
        verts,
        geo.meshes,
        geo.error,
    )
