import struct
import zlib

import pytest

from sourcebridge.formats.binary import FormatError
from sourcebridge.safety import LimitExceeded, Limits, UnsafePath, normalize_game_path, safe_join
from sourcebridge.sources import FolderSource, GmaSource, Mount, open_source


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Models\\Props\\Crate.MDL", "models/props/crate.mdl"),
        ("./materials/x.vmt", "materials/x.vmt"),
        ("a/b/../c.txt", "a/c.txt"),
    ],
)
def test_normalize(raw, expected):
    assert normalize_game_path(raw) == expected


@pytest.mark.parametrize("bad", ["../etc/passwd", "/abs/x", "C:/x", "a/../../x", ""])
def test_unsafe_paths_rejected(bad):
    with pytest.raises(UnsafePath):
        normalize_game_path(bad)


def test_safe_join_stays_inside(tmp_path):
    assert safe_join(tmp_path, "a/b.txt") == (tmp_path / "a/b.txt").resolve()
    with pytest.raises(UnsafePath):
        safe_join(tmp_path, "../x")


def test_open_source_detects_kind(addon_dir, gma_path, vpk_path):
    assert open_source(addon_dir).kind == "folder"
    assert open_source(gma_path).kind == "gma"
    assert open_source(vpk_path).kind == "vpk"


def test_same_content_in_all_source_kinds(addon_dir, gma_path, vpk_path):
    path = "models/sourcebridge/crate.mdl"
    datas = []
    for src in (open_source(addon_dir), open_source(gma_path), open_source(vpk_path)):
        m = Mount([src])
        datas.append(m.read(m.find(path)))
    assert datas[0] == datas[1] == datas[2]


def test_mount_priority_and_shadowing(tmp_path, gma_path):
    override = tmp_path / "override"
    (override / "materials/models/sourcebridge").mkdir(parents=True)
    (override / "materials/models/sourcebridge/CRATE.vmt").write_text('"UnlitGeneric" {}')
    m = Mount([FolderSource(override), GmaSource(gma_path)])
    hit = m.find("materials/models/sourcebridge/crate.vmt")
    assert hit.source == "folder:override"
    assert hit.original_name == "materials/models/sourcebridge/CRATE.vmt"
    copies = m.shadowed("materials/models/sourcebridge/crate.vmt")
    assert [c.source for c in copies] == ["folder:override", "gma:sourcebridge_fixtures.gma"]


def _gma(entries: list[tuple[str, bytes]]) -> bytes:
    body = bytearray(b"GMAD\x03" + struct.pack("<QQ", 0, 0) + b"\0" + b"t\0{}\0a\0" + struct.pack("<i", 1))
    for i, (name, data) in enumerate(entries, 1):
        body += struct.pack("<I", i) + name.encode() + b"\0" + struct.pack("<qI", len(data), zlib.crc32(data))
    body += struct.pack("<I", 0)
    for _, data in entries:
        body += data
    return bytes(body + struct.pack("<I", 0))


def test_gma_with_traversal_entries_is_contained(tmp_path):
    p = tmp_path / "evil.gma"
    p.write_bytes(_gma([("../../evil.txt", b"x"), ("models/ok.mdl", b"y")]))
    src = GmaSource(p)
    assert list(src.list()) == ["models/ok.mdl"]
    assert src.describe()["unsafe_entries"] == ["../../evil.txt"]


def test_gma_entry_limit(tmp_path):
    p = tmp_path / "many.gma"
    p.write_bytes(_gma([(f"f{i}.txt", b"") for i in range(20)]))
    with pytest.raises(FormatError, match="more than 10"):
        GmaSource(p, Limits(max_entries=10))


def test_budget_limits_reads(gma_path):
    m = Mount([GmaSource(gma_path)], Limits(max_file_bytes=100))
    with pytest.raises(LimitExceeded):
        m.read(m.find("models/sourcebridge/crate.mdl"))


def test_folder_source_skips_symlinks(tmp_path):
    root = tmp_path / "addon"
    (root / "models").mkdir(parents=True)
    (tmp_path / "secret.txt").write_text("secret")
    (root / "models" / "link.mdl").symlink_to(tmp_path / "secret.txt")
    assert "models/link.mdl" not in FolderSource(root).list()
