"""Reader for Source 1 collision models (.phy).

A .phy holds one or more solids (IVP compact surfaces made of convex ledges) followed by a
KeyValues text section (mass, surface properties, ragdoll constraints, ...).
Points are stored by IVP in metres with swapped axes; `to_source` converts them to model
space in inches so they line up with the .mdl geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .binary import FormatError, Reader

VPHY_ID = b"VPHY"
IVPS_ID = b"IVPS"
COMPACT_SURFACE_SIZE = 48
LEDGE_HEADER_SIZE = 16
TRIANGLE_SIZE = 16
NODE_SIZE = 28
METERS_TO_INCHES = 1.0 / 0.0254


def ivp_to_source(p: tuple[float, float, float]) -> tuple[float, float, float]:
    """IVP (metres, y down / z forward) -> Source model space (inches, z up)."""
    x, y, z = p
    return (x * METERS_TO_INCHES, z * METERS_TO_INCHES, -y * METERS_TO_INCHES)


@dataclass
class ConvexHull:
    points: list[tuple[float, float, float]]  # Source model/bone space, inches
    triangles: list[tuple[int, int, int]]  # indices into points


@dataclass
class Solid:
    index: int
    model_type: int
    hulls: list[ConvexHull]
    mass_center: tuple[float, float, float]
    legacy: bool


@dataclass
class TextBlock:
    kind: str  # solid, ragdollconstraint, collisionrules, editparams, ...
    values: dict[str, str]


@dataclass
class PhyFile:
    checksum: int
    solids: list[Solid]
    text: str
    blocks: list[TextBlock] = field(default_factory=list)

    def solid_info(self, index: int) -> dict[str, str]:
        for b in self.blocks:
            if b.kind == "solid" and b.values.get("index") == str(index):
                return b.values
        return {}

    @property
    def total_mass(self) -> float | None:
        for b in self.blocks:
            if b.kind == "editparams" and "totalmass" in b.values:
                return float(b.values["totalmass"])
        masses = [float(b.values["mass"]) for b in self.blocks if b.kind == "solid" and "mass" in b.values]
        return sum(masses) if masses else None


def read_phy(data: bytes) -> PhyFile:
    r = Reader(data, "phy")
    if len(data) < 16:
        raise FormatError("phy: file too small")
    size, _id, count, checksum = r.unpack("iiii", 0)
    if size != 16:
        raise FormatError(f"phy: header size {size} (expected 16)")
    if not 0 <= count <= 1024:
        raise FormatError(f"phy: implausible solid count {count}")
    off = 16
    solids = []
    for i in range(count):
        solid_size = r.i32(off)
        body = off + 4
        if r.raw(body, 4) == VPHY_ID:
            _ver, model_type = r.unpack("hh", body + 4)
            surface = body + 28
            legacy = False
        else:
            model_type = 0
            surface = body
            legacy = True
        solids.append(_read_surface(r, i, surface, model_type, legacy))
        off = body + solid_size
    text = data[off:].split(b"\0", 1)[0].decode("utf-8", "replace")
    return PhyFile(checksum, solids, text, parse_text_section(text))


def _read_surface(r: Reader, index: int, s: int, model_type: int, legacy: bool) -> Solid:
    mass_center = ivp_to_source(r.vec3(s))
    tree_root = r.i32(s + 32)
    if r.raw(s + 44, 4) != IVPS_ID:
        raise FormatError(f"phy: solid {index} has no IVPS compact surface id")
    ledges: list[int] = []
    _walk(r, s + tree_root, ledges, depth=0)
    hulls = [_read_ledge(r, lo) for lo in ledges]
    return Solid(index, model_type, hulls, mass_center, legacy)


def _walk(r: Reader, node: int, out: list[int], depth: int) -> None:
    if depth > 64:
        raise FormatError("phy: collision tree deeper than 64 levels")
    right, ledge_rel = r.unpack("ii", node)
    if right == 0:
        if ledge_rel == 0:
            raise FormatError(f"phy: leaf node at {node} has no ledge")
        out.append(node + ledge_rel)
        return
    _walk(r, node + NODE_SIZE, out, depth + 1)
    _walk(r, node + right, out, depth + 1)


def _read_ledge(r: Reader, lo: int) -> ConvexHull:
    point_rel = r.i32(lo)
    ntri = r.i16(lo + 12)
    if ntri <= 0:
        raise FormatError(f"phy: ledge at {lo} has {ntri} triangles")
    points_base = lo + point_rel
    tris_global = []
    for k in range(ntri):
        t = lo + LEDGE_HEADER_SIZE + k * TRIANGLE_SIZE
        e = r.unpack("3I", t + 4)
        tris_global.append(tuple(x & 0xFFFF for x in e))
    used = sorted({i for t in tris_global for i in t})
    remap = {g: n for n, g in enumerate(used)}
    points = [ivp_to_source(r.vec3(points_base + g * 16)) for g in used]
    tris = [(remap[a], remap[b], remap[c]) for a, b, c in tris_global]
    return ConvexHull(points, tris)


def parse_text_section(text: str) -> list[TextBlock]:
    """Parse the flat KeyValues blocks that follow the binary solids."""
    blocks: list[TextBlock] = []
    tokens = _tokens(text)
    i = 0
    while i < len(tokens):
        kind = tokens[i]
        if i + 1 < len(tokens) and tokens[i + 1] == "{":
            values: dict[str, str] = {}
            i += 2
            depth = 1
            while i < len(tokens) and depth:
                tok = tokens[i]
                if tok == "{":
                    depth += 1
                    i += 1
                elif tok == "}":
                    depth -= 1
                    i += 1
                elif depth == 1 and i + 1 < len(tokens) and tokens[i + 1] not in ("{", "}"):
                    key = tok.lower()
                    values[key] = tokens[i + 1] if key not in values else values[key] + "," + tokens[i + 1]
                    i += 2
                else:
                    i += 1
            blocks.append(TextBlock(kind.lower(), values))
        else:
            i += 1
    return blocks


def _tokens(text: str) -> list[str]:
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c in "{}":
            out.append(c)
            i += 1
        elif c == '"':
            j = text.find('"', i + 1)
            j = n if j < 0 else j
            out.append(text[i + 1 : j])
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '{}"':
                j += 1
            out.append(text[i:j])
            i = j
    return out
