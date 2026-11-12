"""Local state the backend keeps. Deliberately small:

- attestations/<sha256>.json  public TEE attestation reports (no data-room content),
                               served to anyone at GET /api/attestations/{hash}
- manifests/<room>.json       per-file hashes recorded at commit time, so a
                               tampered room can say *which* file changed
- rooms/<room>/               uploaded data rooms (the founder's own files)

Questions, answers, and raw TEE requests/responses are never written here.
The investor keeps the receipt bundle; the chain keeps the hashes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .hashing import DataRoomDigest, sha256_hex

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.attestations = self.root / "attestations"
        self.manifests = self.root / "manifests"
        self.rooms = self.root / "rooms"
        self.meta = self.root / "meta"
        for d in (self.attestations, self.manifests, self.rooms, self.meta):
            d.mkdir(parents=True, exist_ok=True)

    # public attestation reports
    def put_attestation(self, data: bytes) -> str:
        h = sha256_hex(data)
        path = self.attestations / f"{h}.json"
        if not path.exists():
            path.write_bytes(data)
        return h

    def get_attestation(self, h: str) -> bytes | None:
        if not _HEX64.match(h or ""):
            return None
        path = self.attestations / f"{h}.json"
        return path.read_bytes() if path.exists() else None

    # commit-time manifests (file paths + hashes only, never contents)
    def save_manifest(self, room_id: str, digest: DataRoomDigest) -> None:
        data = {"root": digest.root, "files": {f.path: f.sha256 for f in digest.files}}
        (self.manifests / f"{room_id}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")

    def load_manifest(self, room_id: str) -> dict | None:
        path = self.manifests / f"{room_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    # per-room metadata: who uploaded it, whether it is sealed, whether this server is approved
    def get_meta(self, room_id: str) -> dict:
        path = self.meta / f"{room_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def put_meta(self, room_id: str, **fields) -> dict:
        data = {**self.get_meta(room_id), **fields}
        (self.meta / f"{room_id}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        return data

    def drop_room(self, room_id: str) -> None:
        import shutil
        shutil.rmtree(self.rooms / room_id, ignore_errors=True)
        for p in (self.meta / f"{room_id}.json", self.manifests / f"{room_id}.json"):
            p.unlink(missing_ok=True)


def changed_files(manifest: dict | None, digest: DataRoomDigest) -> list[str]:
    if not manifest:
        return []
    before = manifest.get("files", {})
    now = {f.path: f.sha256 for f in digest.files}
    return sorted(p for p in set(before) | set(now) if before.get(p) != now.get(p))
