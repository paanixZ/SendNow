"""Bounds-checked little-endian reader shared by the Source 1 binary parsers."""

from __future__ import annotations

import struct


class FormatError(ValueError):
    """Raised when a file does not match the structure a parser expects.

    The message names the file kind and the offending offset so reports can point at it.
    """


class Reader:
    def __init__(self, data: bytes, kind: str):
        self.data = data
        self.kind = kind

    def __len__(self) -> int:
        return len(self.data)

    def check(self, offset: int, size: int) -> None:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise FormatError(
                f"{self.kind}: read of {size} bytes at offset {offset} is outside the file "
                f"({len(self.data)} bytes); the file is truncated or not this format variant"
            )

    def unpack(self, fmt: str, offset: int) -> tuple:
        fmt = "<" + fmt
        size = struct.calcsize(fmt)
        self.check(offset, size)
        return struct.unpack_from(fmt, self.data, offset)

    def i32(self, offset: int) -> int:
        return self.unpack("i", offset)[0]

    def u32(self, offset: int) -> int:
        return self.unpack("I", offset)[0]

    def i16(self, offset: int) -> int:
        return self.unpack("h", offset)[0]

    def u16(self, offset: int) -> int:
        return self.unpack("H", offset)[0]

    def u8(self, offset: int) -> int:
        return self.unpack("B", offset)[0]

    def f32(self, offset: int) -> float:
        return self.unpack("f", offset)[0]

    def vec3(self, offset: int) -> tuple[float, float, float]:
        return self.unpack("3f", offset)

    def raw(self, offset: int, size: int) -> bytes:
        self.check(offset, size)
        return self.data[offset : offset + size]

    def cstr(self, offset: int, limit: int = 4096) -> str:
        """Null-terminated string at an absolute offset. Offset 0 relative strings are empty."""
        self.check(offset, 1)
        end = self.data.find(b"\0", offset, min(len(self.data), offset + limit))
        if end < 0:
            raise FormatError(f"{self.kind}: unterminated string at offset {offset}")
        return self.data[offset:end].decode("utf-8", errors="replace")

    def fixed_str(self, offset: int, size: int) -> str:
        return self.raw(offset, size).split(b"\0", 1)[0].decode("utf-8", errors="replace")

    def rel_str(self, base: int, rel: int) -> str:
        return "" if rel == 0 else self.cstr(base + rel)
