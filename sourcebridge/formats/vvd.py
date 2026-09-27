"""Reader for Source 1 vertex data (.vvd, version 4)."""

from __future__ import annotations

from dataclasses import dataclass

from .binary import FormatError, Reader

VVD_MAGIC = b"IDSV"
VERTEX_SIZE = 48
TANGENT_SIZE = 16


@dataclass
class Vertex:
    weights: tuple[float, ...]
    bones: tuple[int, ...]
    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    uv: tuple[float, float]


@dataclass
class VertexFile:
    version: int
    checksum: int
    num_lods: int
    lod_vertex_counts: tuple[int, ...]
    fixups: list[tuple[int, int, int]]  # (lod, source vertex id, count)
    raw_vertices: list[Vertex]
    tangents: list[tuple[float, float, float, float]]

    def vertices_for_lod(self, lod: int = 0) -> list[Vertex]:
        """Vertex list as the engine sees it for a LOD (fixups applied)."""
        if not self.fixups:
            return self.raw_vertices
        out: list[Vertex] = []
        for fl, src, count in self.fixups:
            if fl >= lod:
                out.extend(self.raw_vertices[src : src + count])
        return out


def read_vvd(data: bytes) -> VertexFile:
    r = Reader(data, "vvd")
    if len(data) < 64 or data[:4] != VVD_MAGIC:
        raise FormatError("vvd: missing IDSV header")
    version, checksum, num_lods = r.unpack("iii", 4)
    if version != 4:
        raise FormatError(f"vvd: version {version} is not supported (supported: 4)")
    lod_counts = r.unpack("8i", 16)
    num_fixups, fixup_start, vertex_start, tangent_start = r.unpack("4i", 48)
    if not 1 <= num_lods <= 8:
        raise FormatError(f"vvd: implausible LOD count {num_lods}")
    fixups = [r.unpack("3i", fixup_start + i * 12) for i in range(num_fixups)]
    total = lod_counts[0]
    verts = []
    for i in range(total):
        o = vertex_start + i * VERTEX_SIZE
        w0, w1, w2, b0, b1, b2, nb = r.unpack("3f3bB", o)
        n = min(max(nb, 1), 3)
        verts.append(
            Vertex(
                weights=(w0, w1, w2)[:n],
                bones=(b0, b1, b2)[:n],
                position=r.vec3(o + 16),
                normal=r.vec3(o + 28),
                uv=r.unpack("2f", o + 40),
            )
        )
    tangents = []
    if tangent_start:
        for i in range(total):
            tangents.append(r.unpack("4f", tangent_start + i * TANGENT_SIZE))
    return VertexFile(version, checksum, num_lods, lod_counts, fixups, verts, tangents)
