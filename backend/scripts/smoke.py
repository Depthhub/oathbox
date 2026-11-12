"""Smoke test: one real question against the NEAR AI Cloud TEE, every check printed.

    python scripts/smoke.py ["Is MRR growing month over month?"]

Reads NEARAI_API_KEY and MODEL_ID from ../.env. Spends one completion's worth of
credits. Saves the (public) attestation report under .oathbox/attestations/.
Never prints data-room contents.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from oathbox.hashing import digest_files, read_room  # noqa: E402
from oathbox.pipeline import ask  # noqa: E402
from oathbox.tee import NearAICloud  # noqa: E402

ICON = {"pass": "PASS ", "fail": "FAIL ", "warn": "WARN ", "error": "ERROR", "skip": "SKIP "}


async def main() -> int:
    load_dotenv(REPO / ".env")
    model = os.getenv("MODEL_ID", "").strip()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_withheld = "--show-withheld" in sys.argv  # debugging the fictional sample room only
    question = args[0] if args else "Is MRR growing month over month?"
    room_dir = REPO / os.getenv("DATAROOM_DIR", "sample-dataroom")

    files = read_room(room_dir)
    digest = digest_files(files)
    print(f"data room : {room_dir.name}  files={digest.file_count}  root={digest.root}")
    print(f"model     : {model}")
    print(f"question  : {question}")

    cloud = NearAICloud(os.getenv("NEARAI_API_KEY", "").strip(), os.getenv("NEARAI_BASE_URL", "https://cloud-api.near.ai"))
    t0 = time.perf_counter()
    try:
        out = await ask(cloud, files, question, model)
    finally:
        await cloud.aclose()
    elapsed = time.perf_counter() - t0

    store = REPO / ".oathbox" / "attestations"
    store.mkdir(parents=True, exist_ok=True)
    (store / f"{out.attestation_hash}.json").write_bytes(out.attestation_bytes)

    print(f"\nanswer ({'delivered' if out.delivered else 'WITHHELD: ' + str(out.filter_reason)}):\n  {out.answer}\n")
    if show_withheld and not out.delivered:
        print(f"[debug] unfiltered answer:\n  {out.raw_answer}\n")
    print("checks:")
    for c in out.checks:
        print(f"  [{ICON.get(c.status, c.status)}] {c.label}" + (f"  ({c.detail})" if c.detail else ""))
    print(f"\nbadge          : {out.badge}")
    print(f"signer         : {out.signature.get('signing_address')}  kind={out.signature.get('signature_kind')}")
    print(f"nonce          : {out.nonce}")
    print(f"request_hash   : {out.request_hash}")
    print(f"response_hash  : {out.response_hash}")
    print(f"attestation    : {out.attestation_hash}")
    print(f"usage          : {out.usage}")
    print(f"elapsed        : {elapsed:.1f}s")
    return 0 if out.badge in ("verified", "verified_with_warnings") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
