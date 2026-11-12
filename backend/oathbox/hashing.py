"""Deterministic data-room hashing.

Rules (identical on every OS, documented in the README):

    rel        = POSIX-style path relative to the data-room folder
    file_hash  = sha256(raw file bytes)              # no newline normalisation
    leaf       = sha256(utf8(rel) || 0x00 || file_hash_raw32)
    root       = sha256(leaf_1 || leaf_2 || ... )     # leaves sorted by utf8(rel)

No Merkle tree: the demo room has ~13 files, and one flat root is easier to
re-derive by hand.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileEntry:
    path: str          # POSIX relative path
    sha256: str        # hex of the raw bytes
    size: int


@dataclass(frozen=True)
class DataRoomDigest:
    root: str                      # hex
    files: tuple[FileEntry, ...]   # sorted by path

    @property
    def file_count(self) -> int:
        return len(self.files)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def leaf_hash(rel_path: str, file_hash_raw: bytes) -> bytes:
    if len(file_hash_raw) != 32:
        raise ValueError("file hash must be 32 raw bytes")
    if "\x00" in rel_path:
        raise ValueError("path may not contain NUL")
    return hashlib.sha256(rel_path.encode("utf-8") + b"\x00" + file_hash_raw).digest()


def list_files(room_dir: Path) -> list[tuple[str, Path]]:
    """Every regular file under room_dir as (posix_rel_path, absolute_path), sorted.

    Symlinks are rejected so a room can't silently pull in files from elsewhere.
    """
    room_dir = Path(room_dir)
    if not room_dir.is_dir():
        raise FileNotFoundError(f"data room not found: {room_dir}")
    out: list[tuple[str, Path]] = []
    for p in room_dir.rglob("*"):
        if p.is_symlink():
            raise ValueError(f"symlinks are not allowed in a data room: {p}")
        if p.is_file():
            out.append((p.relative_to(room_dir).as_posix(), p))
    out.sort(key=lambda t: t[0].encode("utf-8"))
    return out


def read_room(room_dir: Path) -> list[tuple[str, bytes]]:
    """(rel_path, raw bytes) for every file, in canonical order."""
    return [(rel, p.read_bytes()) for rel, p in list_files(room_dir)]


def digest_files(files: list[tuple[str, bytes]]) -> DataRoomDigest:
    """Hash an in-memory room. Input order does not matter."""
    ordered = sorted(files, key=lambda t: t[0].encode("utf-8"))
    paths = [rel for rel, _ in ordered]
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate paths in data room")
    entries: list[FileEntry] = []
    leaves: list[bytes] = []
    for rel, data in ordered:
        raw = hashlib.sha256(data).digest()
        entries.append(FileEntry(path=rel, sha256=raw.hex(), size=len(data)))
        leaves.append(leaf_hash(rel, raw))
    root = hashlib.sha256(b"".join(leaves)).hexdigest()
    return DataRoomDigest(root=root, files=tuple(entries))


def digest_room(room_dir: Path) -> DataRoomDigest:
    return digest_files(read_room(room_dir))
