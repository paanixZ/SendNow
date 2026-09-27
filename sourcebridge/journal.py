"""Change journal: every property of an asset ends up in exactly one traceable state."""

from __future__ import annotations

from dataclasses import asdict, dataclass

STATES = (
    "preserved",  # carried over unchanged
    "converted",  # carried over with an exact, documented transformation
    "approximated",  # carried over, but the target cannot represent it identically
    "estimated",  # value was missing and filled from a documented default/preset
    "generated",  # new data that did not exist in the source
    "lost",  # present in the source, not in the target (still in the archived original)
    "error",  # could not be processed
)


@dataclass
class Entry:
    subject: str
    field: str
    state: str
    detail: str


class Journal:
    def __init__(self):
        self.entries: list[Entry] = []

    def add(self, subject: str, field: str, state: str, detail: str) -> None:
        if state not in STATES:
            raise ValueError(state)
        self.entries.append(Entry(subject, field, state, detail))

    def preserved(self, s, f, d=""):
        self.add(s, f, "preserved", d)

    def converted(self, s, f, d):
        self.add(s, f, "converted", d)

    def approximated(self, s, f, d):
        self.add(s, f, "approximated", d)

    def estimated(self, s, f, d):
        self.add(s, f, "estimated", d)

    def generated(self, s, f, d):
        self.add(s, f, "generated", d)

    def lost(self, s, f, d):
        self.add(s, f, "lost", d)

    def error(self, s, f, d):
        self.add(s, f, "error", d)

    def counts(self) -> dict[str, int]:
        out = {s: 0 for s in STATES}
        for e in self.entries:
            out[e.state] += 1
        return out

    def to_list(self) -> list[dict]:
        return [asdict(e) for e in self.entries]
