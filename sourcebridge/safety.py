"""Resource limits and path safety for untrusted inputs (addons, archives, workshop downloads)."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path


class LimitExceeded(RuntimeError):
    pass


class UnsafePath(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = 512 * 1024 * 1024
    max_archive_bytes: int = 8 * 1024 * 1024 * 1024
    max_entries: int = 200_000
    max_total_read_bytes: int = 16 * 1024 * 1024 * 1024
    max_dependency_depth: int = 16
    max_include_models: int = 64


DEFAULT_LIMITS = Limits()


def normalize_game_path(path: str) -> str:
    """Canonical game-relative path: forward slashes, lower case, no '..' escapes.

    Source resolves game paths case-insensitively, so the lower-cased form is the lookup key.
    """
    p = path.replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    if p.startswith("/") or (len(p) > 1 and p[1] == ":"):
        raise UnsafePath(f"absolute path not allowed in game content: {path!r}")
    norm = posixpath.normpath(p) if p else ""
    if norm == "." or norm == "":
        raise UnsafePath(f"empty path: {path!r}")
    if norm == ".." or norm.startswith("../") or "\0" in norm:
        raise UnsafePath(f"path escapes its root: {path!r}")
    return norm.lower()


def safe_join(root: Path, rel: str) -> Path:
    """Join a game-relative path under root and make sure the result stays inside root."""
    norm = normalize_game_path(rel)
    target = (root / norm).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise UnsafePath(f"{rel!r} resolves outside {root}")
    return target


class Budget:
    """Tracks bytes read across a job so a hostile archive cannot exhaust memory or disk."""

    def __init__(self, limits: Limits = DEFAULT_LIMITS):
        self.limits = limits
        self.read_bytes = 0

    def charge(self, size: int, what: str) -> None:
        if size > self.limits.max_file_bytes:
            raise LimitExceeded(f"{what}: {size} bytes exceeds per-file limit {self.limits.max_file_bytes}")
        self.read_bytes += size
        if self.read_bytes > self.limits.max_total_read_bytes:
            raise LimitExceeded(f"job read more than {self.limits.max_total_read_bytes} bytes")
