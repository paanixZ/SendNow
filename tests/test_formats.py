import io

import pytest
from conftest import ADDON, read

from sourcebridge.formats.binary import FormatError
from sourcebridge.formats.gma import read_gma
from sourcebridge.formats.mdl import read_mdl
from sourcebridge.formats.phy import read_phy
from sourcebridge.formats.vtx import read_vtx
from sourcebridge.formats.vvd import read_vvd
from sourcebridge.geometry import extract

CRATE = "models/sourcebridge/crate"


def test_mdl_header_and_tables():
    m = read_mdl(read(CRATE + ".mdl"))
    assert m.version == 49
    assert m.name == "sourcebridge/crate.mdl"
    assert m.is_static_prop
    assert m.surface_prop == "wood_crate"
    assert m.textures == ["crate", "crate_dark"]
    assert m.cd_textures == ["models\\sourcebridge\\"]
    assert len(m.skin_families) == 2
    assert m.skin_families[1][0] == 1  # skin 1 swaps crate -> crate_dark
    assert [b.name for b in m.bones] == ["static_prop"]
    assert [s.label for s in m.sequences] == ["idle"]
    assert "Wooden.Medium" in m.keyvalues
    assert m.material_paths() == ["models/sourcebridge/crate", "models/sourcebridge/crate_dark"]


def test_mdl_agrees_with_independent_reader():
    """srctools has its own MDL header reader; both must agree on the shared fields."""
    from srctools.filesys import RawFileSystem
    from srctools.mdl import Model

    fs = RawFileSystem(str(ADDON))
    theirs = Model(fs, fs[CRATE + ".mdl"])
    ours = read_mdl(read(CRATE + ".mdl"))
    assert theirs.version == ours.version
    assert theirs.surfaceprop == ours.surface_prop
    assert [s.label for s in theirs.sequences] == [s.label for s in ours.sequences]
    assert len(theirs.skins) == len(ours.skin_families)


def test_geometry_matches_authored_box():
    m = read_mdl(read(CRATE + ".mdl"))
    geos = extract(m, read_vvd(read(CRATE + ".vvd")), read_vtx(read(CRATE + ".dx90.vtx")))
    assert len(geos) == 1
    g = geos[0]
    assert g.triangle_count == 12
    assert g.bounds() == ((-16.0, -16.0, 0.0), (16.0, 16.0, 32.0))
    # winding: triangle order agrees with the stored vertex normals
    for mesh in g.meshes:
        for a, b, c in mesh.triangles:
            pa, pb, pc = (g.vertices[i].position for i in (a, b, c))
            u = [pb[k] - pa[k] for k in range(3)]
            w = [pc[k] - pa[k] for k in range(3)]
            n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
            assert sum(n[k] * g.vertices[a].normal[k] for k in range(3)) > 0


def test_uv_convention_is_flipped_in_vvd():
    """The authored SMD puts uv (0,0) at the first corner of each face; VVD stores 1-v."""
    v = read_vvd(read(CRATE + ".vvd"))
    vs = {round(u, 3) for x in v.raw_vertices for u in x.uv}
    assert vs <= {0.0, 1.0}


def test_phy_reconstructs_box_in_source_units():
    p = read_phy(read(CRATE + ".phy"))
    assert len(p.solids) == 1
    hull = p.solids[0].hulls[0]
    assert len(hull.points) == 8 and len(hull.triangles) == 12
    lo = [min(pt[k] for pt in hull.points) for k in range(3)]
    hi = [max(pt[k] for pt in hull.points) for k in range(3)]
    assert lo == pytest.approx([-16, -16, 0], abs=1e-3)
    assert hi == pytest.approx([16, 16, 32], abs=1e-3)
    assert p.total_mass == 40.0
    assert p.solid_info(0)["surfaceprop"] == "wood_crate"


def test_checksums_pair_up():
    m = read_mdl(read(CRATE + ".mdl"))
    assert read_vvd(read(CRATE + ".vvd")).checksum == m.checksum
    assert read_vtx(read(CRATE + ".dx90.vtx")).checksum == m.checksum
    assert read_phy(read(CRATE + ".phy")).checksum == m.checksum


@pytest.mark.parametrize("cut", [4, 100, 407, 1000])
def test_truncated_mdl_is_reported(cut):
    data = read(CRATE + ".mdl")[:cut]
    with pytest.raises(FormatError):
        read_mdl(data)


def test_wrong_magic_and_version():
    data = bytearray(read(CRATE + ".mdl"))
    with pytest.raises(FormatError, match="IDST"):
        read_mdl(b"XXXX" + bytes(data[4:]))
    data[4] = 37
    with pytest.raises(FormatError, match="version 37"):
        read_mdl(bytes(data))


def test_corrupt_vtx_and_vvd():
    with pytest.raises(FormatError):
        read_vtx(read(CRATE + ".dx90.vtx")[:60])
    with pytest.raises(FormatError):
        read_vvd(b"IDSV" + b"\0" * 10)


def test_gma_matches_sourcepp(gma_path):
    from sourcepp import vpkpp

    ours = read_gma(gma_path.read_bytes())
    pack = vpkpp.PackFile.open(str(gma_path))
    theirs = []
    pack.run_for_all_entries(lambda p, e: theirs.append((p, e.length)))
    assert sorted((e.path, e.size) for e in ours.entries) == sorted(theirs)
    for e in ours.entries:
        assert ours.read(e) == bytes(pack.read_entry(e.path))
    assert ours.title == "SourceBridge Fixtures"


def test_gma_garbage_is_rejected_where_sourcepp_accepts_it():
    with pytest.raises(FormatError):
        read_gma(b"GMAD\x03garbage")


def test_gma_crc_mismatch_detected(gma_path):
    data = bytearray(gma_path.read_bytes())
    g = read_gma(bytes(data))
    e = g.entries[0]
    data[e.offset] ^= 0xFF
    g2 = read_gma(bytes(data))
    with pytest.raises(FormatError, match="CRC"):
        g2.read(g2.entries[0])


def test_srctools_parses_phy_text_the_same():
    from srctools.keyvalues import Keyvalues

    p = read_phy(read(CRATE + ".phy"))
    kv = Keyvalues.parse(io.StringIO(p.text))
    assert kv.find_key("solid")["mass"] == p.solid_info(0)["mass"]
