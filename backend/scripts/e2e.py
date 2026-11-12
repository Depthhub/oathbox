"""End-to-end run against the real stack: NEAR testnet + NEAR AI Cloud TEE.

    python scripts/e2e.py

1. commit the sample data room (once; immutable afterwards)
2. ask one question -> TEE answer + on-chain receipt
3. verify the receipt as an outsider (no bundle) and as the investor (with bundle)
4. tamper on -> ask is refused, nothing recorded -> tamper off
Spends one TEE completion and two small testnet transactions.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from oathbox.app import SAMPLE_ROOM_ID, app  # noqa: E402

ICON = {"pass": "PASS ", "fail": "FAIL ", "warn": "WARN ", "error": "ERROR", "skip": "SKIP ", "na": "n/a  "}


def show_checks(checks):
    for c in checks:
        print(f"    [{ICON.get(c['status'], c['status'])}] {c['label']}" + (f"  ({c['detail']})" if c["detail"] else ""))


def main() -> int:
    with TestClient(app) as c:
        room = SAMPLE_ROOM_ID
        print("== 1. commit data room")
        r = c.post(f"/api/rooms/{room}/commit").json()
        if r.get("already_committed"):
            print("   already committed")
        else:
            print("   tx:", r["tx_url"])
        info = c.get(f"/api/rooms/{room}").json()
        print("   on-chain root:", info["onchain"]["root_hash"], "| matches local:", info["matches_chain"])

        print("\n== 2. ask")
        r = c.post(f"/api/rooms/{room}/ask", json={"question": "Is MRR growing month over month?"})
        a = r.json()
        print("   status:", a.get("status"), "| badge:", a.get("badge"))
        print("   answer:", a.get("answer"))
        if a.get("status") != "answered":
            print(a)
            return 1
        print("   receipt", a["receipt_id"], "tx:", a["tx_url"])

        print("\n== 3a. verify as an outsider (receipt id only)")
        v = c.post("/api/verify", json={"receipt_id": a["receipt_id"]}).json()
        print("   badge:", v["badge"])
        show_checks(v["checks"])

        print("\n== 3b. verify as the investor (with the receipt bundle)")
        v2 = c.post("/api/verify", json={"receipt_id": a["receipt_id"], "bundle": a["bundle"]}).json()
        print("   badge:", v2["badge"])
        show_checks([x for x in v2["checks"] if x["id"] in ("response_hash", "answer_in_response", "answer_hash", "question_hash", "request_hash")])

        print("\n== 3c. a forged bundle fails")
        forged = dict(a["bundle"], answer=a["bundle"]["answer"].replace("Yes", "No", 1))
        v3 = c.post("/api/verify", json={"receipt_id": a["receipt_id"], "bundle": forged}).json()
        print("   badge:", v3["badge"])
        show_checks([x for x in v3["checks"] if x["id"] in ("answer_in_response", "answer_hash")])

        print("\n== 4. tamper demo")
        t = c.post("/api/demo/tamper", json={"on": True}).json()
        print("   tamper on | matches chain:", t["matches_chain"], "| changed:", t["changed_files"])
        try:
            r = c.post(f"/api/rooms/{room}/ask", json={"question": "Is MRR growing month over month?"})
            print("   ask ->", r.status_code, r.json().get("status"), "|", r.json().get("changed_files"))
        finally:
            t = c.post("/api/demo/tamper", json={"on": False}).json()
            print("   tamper off | matches chain:", t["matches_chain"])

        receipts = c.get(f"/api/rooms/{room}/receipts").json()
        print(f"\n== receipts on-chain for {room}: {len(receipts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
