"""Content sources and mount order.

Only sources the user explicitly passes are searched: no silent lookups in random local game
installs. The first source in the list wins, like the search path order in gameinfo.txt; every
shadowed duplicate is recorded so reports can show which copy was used and which were ignored.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from .formats.binary import FormatError
from .formats.gma import read_gma
from .safety import DEFAULT_LIMITS, Budget, LimitExceeded, Limits, UnsafePath, normalize_game_path


@dataclass(frozen=True)
class Hit:
    path: str  # canonical lower-case game path
    source: str  # source id
    original_name: str  # path as stored in the source (original case)
    size: int


class Source:
    id: str
    kind: str
    location: str

    def list(self) -> dict[str, tuple[str, int]]:
        """canonical path -> (original name, size)"""
        raise NotImplementedError

    def read(self, canonical: str) -> bytes:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"id": self.id, "kind": self.kind, "location": self.location}


class FolderSource(Source):
    kind = "folder"

    def __init__(self, root: Path, limits: Limits = DEFAULT_LIMITS, source_id: str | None = None):
        self.root = Path(root)
        if not self.root.is_dir():
            raise FileNotFoundError(f"source folder does not exist: {root}")
        self.location = str(self.root.resolve())
        self.id = source_id or f"folder:{self.root.name}"
        self._index: dict[str, tuple[str, int]] = {}
        count = 0
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            dirnames[:] = [d for d in dirnames if not Path(dirpath, d).is_symlink()]
            for fn in filenames:
                full = Path(dirpath, fn)
                if full.is_symlink():
                    continue
                rel = full.relative_to(self.root).as_posix()
                count += 1
                if count > limits.max_entries:
                    raise LimitExceeded(f"{self.id}: more than {limits.max_entries} files")
                try:
                    key = normalize_game_path(rel)
                except UnsafePath:
                    continue
                self._index.setdefault(key, (rel, full.stat().st_size))

    def list(self):
        return self._index

    def read(self, canonical: str) -> bytes:
        rel, _ = self._index[canonical]
        return (self.root / rel).read_bytes()


class GmaSource(Source):
    kind = "gma"

    def __init__(self, path: Path, limits: Limits = DEFAULT_LIMITS, source_id: str | None = None):
        self.path = Path(path)
        size = self.path.stat().st_size
        if size > limits.max_archive_bytes:
            raise LimitExceeded(f"{path}: archive of {size} bytes exceeds limit")
        self.location = str(self.path.resolve())
        self.id = source_id or f"gma:{self.path.name}"
        self.gma = read_gma(self.path.read_bytes(), limits.max_entries)
        self._index = {}
        self._entries = {}
        for e in self.gma.entries:
            try:
                key = normalize_game_path(e.path)
            except UnsafePath:
                continue  # reported by describe()["unsafe_entries"]
            self._index.setdefault(key, (e.path, e.size))
            self._entries.setdefault(key, e)

    def list(self):
        return self._index

    def read(self, canonical: str) -> bytes:
        return self.gma.read(self._entries[canonical])

    def describe(self) -> dict:
        d = super().describe()
        d.update(
            {
                "title": self.gma.title,
                "author": self.gma.author,
                "gma_version": self.gma.version,
                "steam_id": self.gma.steam_id,
                "metadata": self.gma.metadata,
                "crc_ok": self.gma.crc_ok,
                "unsafe_entries": [e.path for e in self.gma.entries if _unsafe(e.path)],
            }
        )
        return d


class VpkSource(Source):
    kind = "vpk"

    def __init__(self, path: Path, limits: Limits = DEFAULT_LIMITS, source_id: str | None = None):
        from sourcepp import vpkpp

        self.path = Path(path)
        self.location = str(self.path.resolve())
        self.id = source_id or f"vpk:{self.path.name}"
        pack = vpkpp.PackFile.open(str(self.path))
        if pack is None:
            raise FormatError(f"vpk: {path} could not be opened as a VPK")
        self._pack = pack
        self._index = {}
        names: list[tuple[str, int]] = []
        pack.run_for_all_entries(lambda p, e: names.append((p, e.length)))
        if len(names) > limits.max_entries:
            raise LimitExceeded(f"{path}: more than {limits.max_entries} entries")
        for name, length in names:
            try:
                self._index.setdefault(normalize_game_path(name), (name, length))
            except UnsafePath:
                continue

    def list(self):
        return self._index

    def read(self, canonical: str) -> bytes:
        name, _ = self._index[canonical]
        data = self._pack.read_entry(name)
        if data is None:
            raise FormatError(f"vpk: entry {name} could not be read (missing archive chunk?)")
        return bytes(data)


def _unsafe(p: str) -> bool:
    try:
        normalize_game_path(p)
        return False
    except UnsafePath:
        return True


def open_source(path: Path, limits: Limits = DEFAULT_LIMITS) -> Source:
    """Detect the source kind from content, not only the extension."""
    p = Path(path)
    if p.is_dir():
        return FolderSource(p, limits)
    with open(p, "rb") as f:
        head = f.read(4)
    if head == b"GMAD":
        return GmaSource(p, limits)
    if head == b"\x34\x12\xaa\x55" or p.name.endswith("_dir.vpk") or p.suffix == ".vpk":
        return VpkSource(p, limits)
    raise FormatError(f"{p}: not a folder, GMA or VPK (header {head!r})")


@dataclass
class Mount:
    """Ordered list of sources; earlier sources take precedence."""

    sources: list[Source]
    limits: Limits = DEFAULT_LIMITS
    budget: Budget = field(default=None)  # type: ignore[assignment]
    reads: dict[str, Hit] = field(default_factory=dict)

    def __post_init__(self):
        if self.budget is None:
            self.budget = Budget(self.limits)

    def find(self, path: str) -> Hit | None:
        key = normalize_game_path(path)
        for s in self.sources:
            entry = s.list().get(key)
            if entry is not None:
                return Hit(key, s.id, entry[0], entry[1])
        return None

    def shadowed(self, path: str) -> list[Hit]:
        """All copies of a path, in priority order (index 0 is the one used)."""
        key = normalize_game_path(path)
        return [Hit(key, s.id, e[0], e[1]) for s in self.sources if (e := s.list().get(key))]

    def read(self, hit: Hit) -> bytes:
        self.budget.charge(hit.size, hit.path)
        src = next(s for s in self.sources if s.id == hit.source)
        data = src.read(hit.path)
        self.reads[hit.path] = hit
        return data

    def all_paths(self) -> set[str]:
        out: set[str] = set()
        for s in self.sources:
            out.update(s.list())
        return out


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
