"""Demo-only tamper toggle: inflate last month's MRR in metrics.csv after the
room was committed, to show Oathbox refusing to answer over a changed room.

The original bytes are backed up OUTSIDE the data-room folder (so the hashing
walk never sees the backup) and restored exactly, which restores the exact root.
"""

from __future__ import annotations

from pathlib import Path

TARGET = "metrics.csv"
ORIGINAL = b"2026-10,47950,"
TAMPERED = b"2026-10,57950,"


class Tamper:
    def __init__(self, room_dir: Path, state_dir: Path):
        self.file = Path(room_dir) / TARGET
        self.backup = Path(state_dir) / "tamper" / f"{TARGET}.orig"

    @property
    def active(self) -> bool:
        return self.backup.exists()

    def enable(self) -> None:
        if self.active:
            return
        data = self.file.read_bytes()
        if ORIGINAL not in data:
            raise RuntimeError("metrics.csv does not look like the original sample; refusing to tamper")
        self.backup.parent.mkdir(parents=True, exist_ok=True)
        self.backup.write_bytes(data)
        self.file.write_bytes(data.replace(ORIGINAL, TAMPERED, 1))

    def disable(self) -> None:
        if not self.active:
            return
        self.file.write_bytes(self.backup.read_bytes())
        self.backup.unlink()
