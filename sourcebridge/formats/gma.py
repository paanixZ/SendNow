"""Strict reader for Garry's Mod addon packages (.gma, versions 1-3).

Layout as written by Facepunch's open-source gmad. Every entry is bounds- and CRC-checked
because damaged workshop downloads are common and must be reported, not guessed around.
"""

from __future__ import annotations

import json
import zlib
from dataclasses import dataclass

from .binary import FormatError, Reader


@dataclass
class GmaEntry:
    path: str
    size: int
    crc: int
    offset: int


@dataclass
class GmaFile:
    version: int
    steam_id: int
    timestamp: int
    required_content: list[str]
    title: str
    description: str
    author: str
    addon_version: int
    entries: list[GmaEntry]
    data: bytes
    crc_ok: bool | None  # None when the file has no trailing CRC

    @property
    def metadata(self) -> dict:
        try:
            meta = json.loads(self.description)
            return meta if isinstance(meta, dict) else {"description": self.description}
        except ValueError:
            return {"description": self.description}

    def read(self, entry: GmaEntry) -> bytes:
        blob = self.data[entry.offset : entry.offset + entry.size]
        if zlib.crc32(blob) != entry.crc and entry.crc != 0:
            raise FormatError(f"gma: CRC mismatch for {entry.path}")
        return blob


def read_gma(data: bytes, max_entries: int = 200_000) -> GmaFile:
    r = Reader(data, "gma")
    if data[:4] != b"GMAD":
        raise FormatError("gma: missing GMAD header")
    version = r.u8(4)
    if version not in (1, 2, 3):
        raise FormatError(f"gma: version {version} is not supported (supported: 1-3)")
    steam_id, timestamp = r.unpack("QQ", 5)
    off = 21
    required = []
    if version > 1:
        while True:
            s = r.cstr(off)
            off += len(s.encode()) + 1
            if not s:
                break
            required.append(s)
    title = r.cstr(off)
    off += len(title.encode()) + 1
    desc = r.cstr(off, limit=1 << 20)
    off += len(desc.encode()) + 1
    author = r.cstr(off)
    off += len(author.encode()) + 1
    addon_version = r.i32(off)
    off += 4
    raw_entries = []
    while True:
        num = r.u32(off)
        off += 4
        if num == 0:
            break
        if len(raw_entries) >= max_entries:
            raise FormatError(f"gma: more than {max_entries} entries")
        name = r.cstr(off)
        off += len(name.encode()) + 1
        size, crc = r.unpack("qI", off)
        off += 12
        if size < 0:
            raise FormatError(f"gma: negative size for {name}")
        raw_entries.append((name, size, crc))
    entries = []
    for name, size, crc in raw_entries:
        r.check(off, size)
        entries.append(GmaEntry(name, size, crc, off))
        off += size
    crc_ok = None
    if off + 4 <= len(data):
        stored = r.u32(off)
        crc_ok = None if stored == 0 else zlib.crc32(data[:off]) == stored  # gmad often writes 0
    return GmaFile(
        version, steam_id, timestamp, required, title, desc, author, addon_version, entries, data, crc_ok
    )
