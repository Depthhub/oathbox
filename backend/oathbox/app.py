"""Oathbox HTTP API (FastAPI).

    uvicorn oathbox.app:app --port 8000        (from backend/, after `pip install -e .`)

Routes (all JSON, under /api):
  GET  /config                     contract, model, sample room, disclosure rules
  GET  /rooms/{id}                 on-chain commitment vs local files (names/sizes only)
  POST /rooms/{id}/commit          commit a local room's root on NEAR
  POST /rooms                      upload files as a new room and commit it
  POST /rooms/{id}/ask             {question} -> TEE answer + on-chain receipt + bundle
  GET  /rooms/{id}/receipts        receipts for a room (hashes only)
  GET  /receipts/{id}              one on-chain receipt
  GET  /attestations/{sha256}      public attestation report
  POST /verify                     {receipt_id, bundle?} -> every check, pass/fail
  POST /demo/tamper                {on: bool} toggle the sample-room tamper demo
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .auth import Auth, AuthError
from .chain import ChainError, OathboxChain
from .hashing import digest_files, read_room, sha256_hex
from .pipeline import ask as run_ask
from .prompt import DISCLOSURE_RULES, build_request_body
from .store import Store, changed_files
from .tamper import Tamper
from .tee import NearAICloud, TEEError, answer_text
from .verify import (
    FAIL, NA, PASS, Check, badge, check_model_report, check_receipt_signature,
)

REPO = Path(__file__).resolve().parents[2]
load_dotenv(REPO / ".env")

MODEL_ID = os.getenv("MODEL_ID", "").strip()
NETWORK = os.getenv("NEAR_NETWORK", "testnet")
SAMPLE_ROOM_ID = os.getenv("SAMPLE_ROOM_ID", "ledgerlight-demo")
SAMPLE_DIR = REPO / os.getenv("DATAROOM_DIR", "sample-dataroom")
STATE_DIR = REPO / ".oathbox"
WEB_DIST = REPO / "web" / "dist"
# The whole room goes into the model's context on every question, so keep it small.
MAX_UPLOAD_BYTES = 300_000
MAX_UPLOAD_FILES = 100
_ROOM_ID = re.compile(r"^[a-z0-9_-]{1,64}$")

# Founders seal rooms from their own wallet: one transaction, two calls.
SEAL_GAS = str(50 * 10**12)              # per call
COMMIT_DEPOSIT_YOCTO = str(5 * 10**22)   # 0.05 NEAR; the contract keeps the storage cost, refunds the rest
BACKEND_DEPOSIT_YOCTO = str(10**22)      # 0.01 NEAR, same
PENDING_TTL_S = 3600                     # an unsealed upload holds its name for an hour

store = Store(STATE_DIR)
tamper = Tamper(SAMPLE_DIR, STATE_DIR)
auth = Auth(STATE_DIR, os.getenv("OATHBOX_SESSION_SECRET", "").strip() or None)
_write_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0))
    app.state.cloud = NearAICloud(
        os.getenv("NEARAI_API_KEY", "").strip(),
        os.getenv("NEARAI_BASE_URL", "https://cloud-api.near.ai"),
        http=app.state.http,
    )
    app.state.chain = OathboxChain(
        os.getenv("CONTRACT_ID", "").strip(),
        os.getenv("NEAR_ACCOUNT_ID", "").strip() or None,
        os.getenv("NEAR_PRIVATE_KEY", "").strip() or None,
        network=NETWORK,
        rpc_url=os.getenv("NEAR_RPC_URL", "").strip() or None,
    )
    yield
    await app.state.http.aclose()


app = FastAPI(title="Oathbox", version=__version__, lifespan=lifespan)


@app.exception_handler(ChainError)
async def _chain_error(_, exc: ChainError):
    return JSONResponse(status_code=502, content={"detail": f"NEAR: {exc}"})


@app.exception_handler(TEEError)
async def _tee_error(_, exc: TEEError):
    return JSONResponse(status_code=502, content={"detail": f"NEAR AI Cloud: {exc}"})


# ---------------------------------------------------------------- helpers
def _room_dir(room_id: str) -> Path:
    if not _ROOM_ID.match(room_id):
        raise HTTPException(400, "room id may only use a-z, 0-9, - and _ (max 64)")
    return SAMPLE_DIR if room_id == SAMPLE_ROOM_ID else store.rooms / room_id


def _chain(app_: FastAPI = app) -> OathboxChain:
    return app_.state.chain


async def _onchain_room(room_id: str) -> dict | None:
    return await asyncio.to_thread(_chain().get_dataroom, room_id)


def _local(room_id: str):
    room_dir = _room_dir(room_id)
    if not room_dir.is_dir():
        return None, None
    files = read_room(room_dir)
    return files, digest_files(files)


def viewer(authorization: str | None = Header(default=None)) -> str | None:
    """The signed-in founder's NEAR account, or None."""
    if authorization and authorization.lower().startswith("bearer "):
        return auth.account_for(authorization[7:].strip())
    return None


def founder(account: str | None = Depends(viewer)) -> str:
    if not account:
        raise HTTPException(401, "Connect your NEAR wallet first.")
    return account


def _owner(room_id: str, onchain: dict | None) -> str | None:
    return onchain["owner"] if onchain else store.get_meta(room_id).get("owner")


async def _server_approved(room_id: str, onchain: dict) -> bool:
    """Can this server record receipts for the room? (owner, or allow-listed by the owner)"""
    server = _chain().account_id
    if not server:
        return False
    if onchain["owner"] == server or store.get_meta(room_id).get("backend_approved"):
        return True
    ok = server in await asyncio.to_thread(_chain().get_backends, room_id)
    if ok:
        store.put_meta(room_id, backend_approved=True)
    return ok


def _approve_call(room_id: str) -> dict:
    return {"method": "set_backend", "args": {"dataroom_id": room_id, "account": _chain().account_id},
            "gas": SEAL_GAS, "deposit": BACKEND_DEPOSIT_YOCTO}


def _seal_tx(room_id: str, digest) -> dict:
    """Everything the founder's wallet needs: ONE transaction, two calls (seal + approve this server)."""
    return {
        "receiver_id": _chain().contract_id,
        "calls": [
            {"method": "commit_dataroom",
             "args": {"id": room_id, "root_hash": digest.root, "file_count": digest.file_count},
             "gas": SEAL_GAS, "deposit": COMMIT_DEPOSIT_YOCTO},
            _approve_call(room_id),
        ],
    }


def _room_view(room_id: str, onchain: dict | None, digest, who: str | None = None) -> dict:
    chain = _chain()
    is_sample = room_id == SAMPLE_ROOM_ID
    owner = _owner(room_id, onchain)
    # File names are the founder's business: only the owner (or anyone, for the public sample) sees them.
    can_see = is_sample or (who is not None and who == owner)
    local = None
    if digest is not None:
        local = {"root": digest.root, "file_count": digest.file_count}
        if can_see:
            local["files"] = [{"path": f.path, "size": f.size} for f in digest.files]
    meta = store.get_meta(room_id)
    is_owner = bool(who and who == owner)
    approved = bool(onchain and (onchain["owner"] == chain.account_id or meta.get("backend_approved")))
    next_tx = None  # the wallet transaction the owner still has to send, if any
    if is_owner and not is_sample:
        if onchain is None and digest is not None:
            next_tx = _seal_tx(room_id, digest)
        elif onchain is not None and not approved:
            next_tx = {"receiver_id": chain.contract_id, "calls": [_approve_call(room_id)]}
    return {
        "id": room_id,
        "is_sample": is_sample,
        "owner": owner,
        "is_owner": is_owner,
        "status": "sealed" if onchain else ("pending" if digest is not None else "unknown"),
        "backend_approved": approved,
        "next_transaction": next_tx,
        "onchain": onchain,
        "local": local,
        "matches_chain": bool(onchain and digest and onchain["root_hash"] == digest.root),
        "changed_files": changed_files(store.load_manifest(room_id), digest) if (digest and can_see) else [],
        "tamper_active": tamper.active if is_sample else False,
        "contract_url": chain.account_url(),
    }


# ---------------------------------------------------------------- routes
@app.get("/api/config")
async def config():
    chain = _chain()
    return {
        "version": __version__,
        "network": NETWORK,
        "contract_id": chain.contract_id,
        "contract_url": chain.account_url(),
        "signer": chain.account_id,
        "model_id": MODEL_ID,
        "sample_room_id": SAMPLE_ROOM_ID,
        "disclosure_rules": list(DISCLOSURE_RULES),
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_upload_files": MAX_UPLOAD_FILES,
        "backend_account": chain.account_id,
    }


# ---------------------------------------------------------------- founder sign-in
@app.get("/api/auth/challenge")
async def auth_challenge():
    return auth.challenge()


class SignInBody(BaseModel):
    account_id: str = Field(min_length=2, max_length=64)
    public_key: str = Field(min_length=10, max_length=200)
    signature: str = Field(min_length=10, max_length=200)
    nonce: str = Field(min_length=10, max_length=100)
    callback_url: str | None = Field(default=None, max_length=2000)


@app.post("/api/auth/verify")
async def auth_verify(body: SignInBody):
    chain = _chain()

    def check():
        return auth.verify(
            account_id=body.account_id, public_key=body.public_key, signature=body.signature,
            nonce=body.nonce, callback_url=body.callback_url, is_full_access_key=chain.is_full_access_key,
        )

    try:
        token = await asyncio.to_thread(check)
    except AuthError as e:
        raise HTTPException(401, str(e)) from e
    return {"account_id": body.account_id, "token": token}


@app.get("/api/auth/me")
async def auth_me(account: str | None = Depends(viewer)):
    return {"account_id": account}


# ---------------------------------------------------------------- rooms
@app.get("/api/rooms")
async def list_rooms(account: str | None = Depends(viewer)):
    """The signed-in founder's own rooms. (The bundled sample room is not listed;
    it stays reachable by its link for scripts/e2e.py.)"""
    out: list[dict] = []
    if not account:
        return out
    for p in sorted(store.rooms.iterdir()):
        if not (p.is_dir() and _ROOM_ID.match(p.name)):
            continue
        meta = store.get_meta(p.name)
        owner = meta.get("owner")
        if owner is None:  # rooms from before wallet sign-in: learn the owner from NEAR once
            onchain = await _onchain_room(p.name)
            owner = onchain["owner"] if onchain else None
            if owner:
                meta = store.put_meta(p.name, owner=owner, status="sealed")
        if owner == account:
            out.append({"id": p.name, "is_sample": False, "status": meta.get("status", "pending")})
    return out


@app.get("/api/rooms/{room_id}")
async def get_room(room_id: str, account: str | None = Depends(viewer)):
    _, digest = _local(room_id)
    onchain = await _onchain_room(room_id)
    if onchain is None and digest is None:
        raise HTTPException(404, "unknown data room")
    return _room_view(room_id, onchain, digest, account)


@app.post("/api/rooms/{room_id}/commit")
async def commit_room(room_id: str):
    """Operator-only: seal the bundled sample room with the server's own account.
    Founders seal their rooms from their own wallet instead (see /confirm)."""
    if room_id != SAMPLE_ROOM_ID:
        raise HTTPException(403, "Seal this room from your own NEAR wallet.")
    _, digest = _local(room_id)
    if digest is None:
        raise HTTPException(404, "no local files for this room")
    if room_id == SAMPLE_ROOM_ID and tamper.active:
        raise HTTPException(409, "turn the tamper demo off before committing")
    existing = await _onchain_room(room_id)
    if existing:
        return {"already_committed": True, "room": _room_view(room_id, existing, digest)}
    async with _write_lock:
        room, tx = await asyncio.to_thread(_chain().commit_dataroom, room_id, digest.root, digest.file_count)
    store.save_manifest(room_id, digest)
    return {"already_committed": False, "tx": tx, "tx_url": _chain().tx_url(tx),
            "room": _room_view(room_id, room, digest)}


@app.post("/api/rooms")
async def upload_room(room_id: str = Form(...), files: list[UploadFile] = File(...),
                      account: str = Depends(founder)):
    """Stage files for the signed-in founder. Nothing is sealed yet: the founder's own
    wallet seals it on NEAR next, then calls /confirm."""
    if room_id == SAMPLE_ROOM_ID:
        raise HTTPException(400, "That name is reserved for the sample room.")
    room_dir = _room_dir(room_id)
    if await _onchain_room(room_id):
        raise HTTPException(409, "That room name is taken. Pick another.")
    if room_dir.exists():
        meta = store.get_meta(room_id)
        stale = meta.get("created_at", 0) < time.time() - PENDING_TTL_S
        if meta.get("status") != "pending" or (meta.get("owner") != account and not stale):
            raise HTTPException(409, "That room name is taken. Pick another.")
        store.drop_room(room_id)  # the same founder re-uploading, or an abandoned upload
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(413, f"Too many files: {len(files)} (max {MAX_UPLOAD_FILES}).")
    total, staged, seen = 0, [], set()
    for f in files:
        rel = (f.filename or "").replace("\\", "/").strip("/")
        parts = rel.split("/")
        if not rel or any(p in ("", ".", "..") for p in parts) or ":" in rel:
            raise HTTPException(400, f"Bad file name: {rel!r}")
        if rel in seen:
            raise HTTPException(400, f"Duplicate file name: {rel}")
        seen.add(rel)
        data = await f.read()
        total += len(data)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"Room is too large: the limit is {MAX_UPLOAD_BYTES // 1000} KB in total.")
        staged.append((rel, data))
    if not staged:
        raise HTTPException(400, "Add at least one file.")
    try:
        for rel, data in staged:
            dest = room_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    except OSError:
        shutil.rmtree(room_dir, ignore_errors=True)
        raise
    _, digest = _local(room_id)
    store.put_meta(room_id, owner=account, status="pending", root=digest.root,
                   file_count=digest.file_count, created_at=int(time.time()), backend_approved=False)
    return {
        "room_id": room_id,
        "root_hash": digest.root,
        "file_count": digest.file_count,
        "transaction": _seal_tx(room_id, digest),
        "room": _room_view(room_id, None, digest, account),
    }


@app.post("/api/rooms/{room_id}/confirm")
async def confirm_room(room_id: str, account: str = Depends(founder)):
    """After the founder's wallet sealed the room: check NEAR says exactly what we staged."""
    _, digest = _local(room_id)
    if digest is None:
        raise HTTPException(404, "No uploaded files for this room.")
    onchain = await _onchain_room(room_id)
    if onchain is None:
        raise HTTPException(409, "NEAR doesn't show this room as sealed yet. If you approved it, try again in a few seconds.")
    if onchain["owner"] != account:
        raise HTTPException(403, f"This room was sealed by {onchain['owner']}, not {account}.")
    if onchain["root_hash"] != digest.root:
        raise HTTPException(409, "The fingerprint on NEAR doesn't match the uploaded files.")
    store.save_manifest(room_id, digest)
    store.put_meta(room_id, status="sealed")
    await _server_approved(room_id, onchain)
    return _room_view(room_id, onchain, digest, account)


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@app.post("/api/rooms/{room_id}/ask")
async def ask_room(room_id: str, body: AskBody):
    chain = _chain()
    files, digest = _local(room_id)
    if digest is None:
        raise HTTPException(404, "no local files for this room")
    onchain = await _onchain_room(room_id)
    if onchain is None:
        raise HTTPException(409, "This room isn't sealed on NEAR yet.")
    if not await _server_approved(room_id, onchain):
        return JSONResponse(status_code=409, content={
            "status": "server_not_approved",
            "detail": "The founder hasn't approved this Oathbox server to record receipts for this room yet.",
        })

    # 1. the room must be byte-identical to what was committed
    if onchain["root_hash"] != digest.root:
        return JSONResponse(status_code=409, content={
            "status": "room_changed",
            "detail": "Data room changed since it was committed. Nothing was asked and nothing was recorded.",
            "onchain_root": onchain["root_hash"],
            "local_root": digest.root,
            "changed_files": changed_files(store.load_manifest(room_id), digest),
        })

    # 2-4. attest -> exact-bytes completion -> signature -> disclosure filter
    out = await run_ask(app.state.cloud, files, body.question, MODEL_ID)
    att_hash = store.put_attestation(out.attestation_bytes)  # public, no room data
    if not out.delivered:
        return {"status": "withheld", "answer": out.answer, "reason": out.filter_reason,
                "badge": out.badge, "checks": [c.to_dict() for c in out.checks]}

    att_checks = [c for c in out.checks if not c.id.startswith("sig_") and c.id != "signer_in_report"]
    att_ok = badge(att_checks) in ("verified", "verified_with_warnings")
    sig_hex = str(out.signature.get("signature", "")).lower()
    sig_hex = sig_hex if sig_hex.startswith("0x") else "0x" + sig_hex

    # 5. receipt on NEAR
    async with _write_lock:
        receipt_id, tx = await asyncio.to_thread(
            chain.record_receipt,
            dataroom_id=room_id,
            dataroom_root=digest.root,
            question_hash=out.question_hash,
            answer_hash=out.answer_hash,
            request_hash=out.request_hash,
            response_hash=out.response_hash,
            completion_sig=sig_hex,
            model_id=out.model,
            attestation_hash=att_hash,
            nonce=out.nonce,
            attestation_checked_offchain=att_ok,
        )

    bundle = {
        "format": "oathbox-receipt-bundle/1",
        "receipt_id": receipt_id,
        "contract_id": chain.contract_id,
        "network": NETWORK,
        "dataroom_id": room_id,
        "question": body.question.strip(),
        "answer": out.answer,
        "model_id": out.model,
        "nonce": out.nonce,
        "attestation_hash": att_hash,
        "signature": out.signature,
        "raw_response_b64": base64.b64encode(out.response_bytes).decode("ascii"),
    }
    return {
        "status": "answered",
        "answer": out.answer,
        "receipt_id": receipt_id,
        "tx": tx,
        "tx_url": chain.tx_url(tx),
        "badge": out.badge,
        "checks": [c.to_dict() for c in out.checks],
        "bundle": bundle,
    }


@app.get("/api/rooms/{room_id}/receipts")
async def room_receipts(room_id: str, from_index: int = 0, limit: int = 50):
    _room_dir(room_id)
    return await asyncio.to_thread(_chain().get_receipts, room_id, from_index, limit)


@app.get("/api/receipts/{receipt_id}")
async def get_receipt(receipt_id: int):
    r = await asyncio.to_thread(_chain().get_receipt, receipt_id)
    if r is None:
        raise HTTPException(404, "no such receipt")
    return r


@app.get("/api/attestations/{att_hash}")
async def get_attestation(att_hash: str):
    data = store.get_attestation(att_hash)
    if data is None:
        raise HTTPException(404, "attestation report not found")
    return Response(content=data, media_type="application/json")


class VerifyBody(BaseModel):
    receipt_id: int
    bundle: dict | None = None


@app.post("/api/verify")
async def verify(body: VerifyBody):
    chain = _chain()
    receipt = await asyncio.to_thread(chain.get_receipt, body.receipt_id)
    if receipt is None:
        raise HTTPException(404, "no such receipt")
    room = await asyncio.to_thread(chain.get_dataroom, receipt["dataroom_id"])
    checks: list[Check] = [
        Check("root_committed", "Receipt is for the data-room root committed on NEAR",
              PASS if room and room["root_hash"] == receipt["dataroom_root"] else FAIL,
              receipt["dataroom_root"]),
    ]

    # Public attestation report, by the hash stored on-chain
    report_bytes = store.get_attestation(receipt["attestation_hash"])
    if report_bytes is None or sha256_hex(report_bytes) != receipt["attestation_hash"]:
        checks.append(Check("attestation_available", "Attestation report matches the on-chain hash", FAIL,
                            "report not found"))
    else:
        checks.append(Check("attestation_available", "Attestation report matches the on-chain hash", PASS))
        report = json.loads(report_bytes)
        candidates = report.get("model_attestations") or []
        sig_checks, signer = check_receipt_signature(receipt, {c.get("signing_address", "") for c in candidates})
        match = next((c for c in candidates if signer and c.get("signing_address", "").lower() == signer.lower()), None)
        if match is None:
            checks.append(Check("signer_in_report", "Signer appears in the attestation report", FAIL))
        else:
            verdict = await check_model_report(match, receipt["nonce"], app.state.http)
            checks.extend(verdict.checks)
        checks.extend(sig_checks)

    # Holder-of-bundle checks (the investor's own copy)
    b = body.bundle
    if b:
        raw = base64.b64decode(b.get("raw_response_b64", "") or "")
        checks.append(Check("response_hash", "Your saved TEE response matches the on-chain response hash",
                            PASS if sha256_hex(raw) == receipt["response_hash"] else FAIL))
        try:
            content_ok = answer_text(json.loads(raw)) == b.get("answer")
        except (ValueError, TEEError):
            content_ok = False
        checks.append(Check("answer_in_response", "Your answer is exactly what the TEE returned",
                            PASS if content_ok else FAIL))
        checks.append(Check("answer_hash", "Answer matches the on-chain answer hash",
                            PASS if sha256_hex(str(b.get("answer", "")).encode()) == receipt["answer_hash"] else FAIL))
        checks.append(Check("question_hash", "Question matches the on-chain question hash",
                            PASS if sha256_hex(str(b.get("question", "")).strip().encode()) == receipt["question_hash"] else FAIL))
    else:
        checks.append(Check("bundle", "Question/answer hashes (needs the investor's receipt bundle)", NA,
                            "load your receipt bundle to run these"))

    # Founder-side: rebuild the exact request bytes from the private room + question
    files, digest = _local(receipt["dataroom_id"])
    if b and digest is not None and digest.root == receipt["dataroom_root"]:
        rebuilt = build_request_body(receipt["model_id"], files, str(b.get("question", "")))
        checks.append(Check("request_hash", "Founder-side: request rebuilt from the private room matches",
                            PASS if sha256_hex(rebuilt) == receipt["request_hash"] else FAIL))
    else:
        checks.append(Check("request_hash", "Founder-side: rebuild the request from the private room", NA,
                            "needs the founder's private files and the question"))

    return {
        "receipt": receipt,
        "badge": badge(checks),
        "checks": [c.to_dict() for c in checks],
        "links": {"contract": chain.account_url(),
                  "attestation": f"/api/attestations/{receipt['attestation_hash']}"},
    }


class TamperBody(BaseModel):
    on: bool


@app.post("/api/demo/tamper")
async def demo_tamper(body: TamperBody):
    try:
        tamper.enable() if body.on else tamper.disable()
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    _, digest = _local(SAMPLE_ROOM_ID)
    onchain = await _onchain_room(SAMPLE_ROOM_ID)
    return _room_view(SAMPLE_ROOM_ID, onchain, digest)


# ---------------------------------------------------------------- web UI
if WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        # Static files copied from web/public (logo, icons); never anything outside dist.
        if path:
            target = (WEB_DIST / path).resolve()
            if target.is_file() and WEB_DIST.resolve() in target.parents:
                return FileResponse(target)
        # index.html names the hashed bundles, so never let a browser keep a stale copy
        return FileResponse(WEB_DIST / "index.html", headers={"Cache-Control": "no-cache"})
