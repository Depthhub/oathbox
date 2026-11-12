"""Attestation and completion-signature verification, as a list of named checks.

Ported from the NEAR AI Cloud reference helpers (docs.near.ai/cloud/verification/
reference: quote-nonce-signer, response-signature-verification) and
nearai/nearai-cloud-verifier (MIT). Fail closed: anything missing or malformed fails.

Each check is pass / fail / warn / error / skip:
  fail  - the evidence is wrong (never "Verified")
  error - we could not finish checking (e.g. collateral server unreachable)
  skip  - depends on an earlier check that did not complete
  warn  - genuine, but below the preferred policy (e.g. TCB OutOfDate)
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from hmac import compare_digest

import dcap_qvl
import httpx
from eth_account import Account
from eth_account.messages import encode_defunct

PASS, FAIL, WARN, ERROR, SKIP, NA = "pass", "fail", "warn", "error", "skip", "na"
# NA = not applicable to this viewer (e.g. founder-side checks shown to an outside
# verifier). It never counts towards or against the badge.

ACCEPTED_TCB = frozenset({"UpToDate"})
WARN_TCB = frozenset({"OutOfDate", "SWHardeningNeeded", "ConfigurationNeeded", "ConfigurationAndSWHardeningNeeded"})
NRAS_URL = "https://nras.attestation.nvidia.com/v3/attest/gpu"


@dataclass
class Check:
    id: str
    label: str
    status: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def badge(checks: list[Check]) -> str:
    """verified | verified_with_warnings | attestation_fetched | failed"""
    statuses = {c.status for c in checks if c.status != NA}
    if not statuses:
        return "attestation_fetched"
    if FAIL in statuses:
        return "failed"
    if ERROR in statuses or SKIP in statuses:
        return "attestation_fetched"
    if WARN in statuses:
        return "verified_with_warnings"
    return "verified"


def _json(v):
    return json.loads(v) if isinstance(v, str) else v


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex_bytes(value: str, expected_len: int | None = None) -> bytes:
    raw = bytes.fromhex(str(value).removeprefix("0x").removeprefix("0X"))
    if expected_len is not None and len(raw) != expected_len:
        raise ValueError(f"expected {expected_len} bytes, got {len(raw)}")
    return raw


def replay_rtmr3(event_log) -> bytes:
    rtmr3 = bytes(48)
    for event in _json(event_log):
        if event.get("imr") != 3:
            continue
        digest = hashlib.sha384(
            struct.pack("<I", event["event_type"])
            + b":"
            + event["event"].encode("utf-8")
            + b":"
            + bytes.fromhex(event.get("event_payload") or "")
        ).digest()
        if event.get("digest") and bytes.fromhex(event["digest"]) != digest:
            raise ValueError(f"digest mismatch for event {event['event']!r}")
        rtmr3 = hashlib.sha384(rtmr3 + digest).digest()
    return rtmr3


def _td_body(verified) -> dict:
    report = json.loads(verified.to_json())["report"]
    td = report.get("TD10") or report.get("TD15")
    if td is None:
        raise ValueError(f"not a TDX report: {sorted(report)}")
    if "report_data" not in td and isinstance(td.get("base"), dict):
        td = td["base"]
    return td


@dataclass
class ModelVerdict:
    signing_address: str
    signing_algo: str
    checks: list[Check]

    @property
    def signer_trusted(self) -> bool:
        return badge(self.checks) in ("verified", "verified_with_warnings")


async def check_model_report(
    report: dict, nonce_hex: str, http: httpx.AsyncClient, pccs_url: str | None = None
) -> ModelVerdict:
    checks: list[Check] = []
    addr = str(report.get("signing_address", ""))
    algo = str(report.get("signing_algo", ""))
    verdict = ModelVerdict(addr, algo, checks)

    checks.append(
        Check(
            "nonce_echo",
            "Report was generated for our fresh nonce",
            PASS if str(report.get("request_nonce", "")).lower() == nonce_hex.lower() else FAIL,
        )
    )

    try:
        if algo != "ecdsa":
            raise ValueError(f"unsupported signing_algo {algo!r}")
        identity = _hex_bytes(addr, 20)
    except ValueError as e:
        checks.append(Check("signer_format", "Signing address is a valid ECDSA address", FAIL, str(e)))
        return verdict

    # 1. Intel TDX quote, verified against Intel collateral
    td = None
    try:
        quote_bytes = bytes.fromhex(report["intel_quote"])
        if pccs_url:
            verified = await dcap_qvl.get_collateral_and_verify(quote_bytes, pccs_url)
        else:
            verified = await dcap_qvl.get_collateral_and_verify(quote_bytes)
    except RuntimeError as e:
        checks.append(Check("tdx_quote", "Intel TDX quote is genuine", ERROR, f"collateral fetch failed: {e}"))
    except (ValueError, KeyError) as e:
        checks.append(Check("tdx_quote", "Intel TDX quote is genuine", FAIL, str(e)))
    else:
        status = verified.status
        if status in ACCEPTED_TCB:
            checks.append(Check("tdx_quote", "Intel TDX quote is genuine", PASS, f"TCB status {status}"))
        elif status in WARN_TCB:
            checks.append(
                Check("tdx_quote", "Intel TDX quote is genuine", WARN,
                      f"TCB status {status}; advisories {list(getattr(verified, 'advisory_ids', []) or [])}")
            )
        else:
            checks.append(Check("tdx_quote", "Intel TDX quote is genuine", FAIL, f"TCB status {status}"))
        try:
            td = _td_body(verified)
        except (ValueError, KeyError) as e:
            checks.append(Check("tdx_body", "Quote body readable", FAIL, str(e)))

    dependent = [
        ("tdx_not_debug", "TEE is not in debug mode"),
        ("signer_bound", "Signing key is bound into the quote"),
        ("nonce_bound", "Our nonce is bound into the quote"),
        ("compose_measured", "Workload config (app_compose) matches the quote"),
        ("event_log", "Event log replays to the measured RTMR3"),
    ]
    if td is None:
        checks.extend(Check(cid, label, SKIP, "needs a verified quote") for cid, label in dependent)
    else:
        debug = bytes.fromhex(td["td_attributes"])[0] & 1
        checks.append(Check("tdx_not_debug", dependent[0][1], FAIL if debug else PASS))

        report_data = bytes.fromhex(td["report_data"])
        fingerprint = report.get("tls_cert_fingerprint")
        prefix = (
            hashlib.sha256(identity + bytes.fromhex(fingerprint)).digest() if fingerprint else identity.ljust(32, b"\0")
        )
        checks.append(Check("signer_bound", dependent[1][1], PASS if compare_digest(report_data[:32], prefix) else FAIL,
                            addr))
        checks.append(Check("nonce_bound", dependent[2][1],
                            PASS if compare_digest(report_data[32:64], bytes.fromhex(nonce_hex)) else FAIL))

        try:
            app_compose = _json(_json(report["info"])["tcb_info"])["app_compose"]
            expected = b"\x01" + hashlib.sha256(app_compose.encode("utf-8")).digest() + bytes(15)
            ok = bytes.fromhex(td["mr_config_id"]) == expected
            checks.append(Check("compose_measured", dependent[3][1], PASS if ok else FAIL))
        except (KeyError, ValueError, TypeError) as e:
            checks.append(Check("compose_measured", dependent[3][1], FAIL, f"missing app_compose: {e}"))

        try:
            ok = replay_rtmr3(report["event_log"]) == bytes.fromhex(td["rt_mr3"])
            checks.append(Check("event_log", dependent[4][1], PASS if ok else FAIL))
        except (KeyError, ValueError, TypeError) as e:
            checks.append(Check("event_log", dependent[4][1], FAIL, str(e)))

    checks.extend(await check_gpu(report, nonce_hex, http))
    return verdict


def _jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


async def check_gpu(report: dict, nonce_hex: str, http: httpx.AsyncClient) -> list[Check]:
    label_nonce = "GPU evidence is for our nonce"
    label_nras = "NVIDIA attestation service accepts the GPU (JWT signature not checked)"
    raw = report.get("nvidia_payload")
    if not raw:
        return [Check("gpu_nonce", label_nonce, FAIL, "no GPU evidence"), Check("gpu_nras", label_nras, SKIP)]
    payload = _json(raw)
    out = [Check("gpu_nonce", label_nonce,
                 PASS if str(payload.get("nonce", "")).lower() == nonce_hex.lower() else FAIL)]
    try:
        r = await http.post(NRAS_URL, json=payload, headers={"Accept": "application/json"}, timeout=60)
        r.raise_for_status()
        token = r.json()[0][1]
        claims = _jwt_claims(token)
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
        out.append(Check("gpu_nras", label_nras, ERROR, f"NRAS unavailable: {type(e).__name__}"))
        return out
    ok = claims.get("x-nvidia-overall-att-result") is True
    eat = str(claims.get("eat_nonce", "")).lower()
    if ok and eat and eat != nonce_hex.lower():
        out.append(Check("gpu_nras", label_nras, FAIL, "NRAS token is for a different nonce"))
    else:
        out.append(Check("gpu_nras", label_nras, PASS if ok else FAIL))
    return out


def signature_text(model: str, request_bytes: bytes, response_bytes: bytes) -> str:
    return f"{model}:{sha256_hex(request_bytes)}:{sha256_hex(response_bytes)}"


def check_signature(
    signature: dict, *, model: str, request_bytes: bytes, response_bytes: bytes, trusted_signers: set[str]
) -> list[Check]:
    checks: list[Check] = []
    kind = signature.get("signature_kind")
    checks.append(Check("sig_kind", "Answer was signed by the model's TEE (not the gateway)",
                        PASS if kind == "provider_tee" else FAIL, str(kind)))

    expected = signature_text(model, request_bytes, response_bytes)
    checks.append(Check("sig_covers_exchange", "Signature covers this exact question and answer",
                        PASS if signature.get("text") == expected else FAIL))

    label = "Signature is valid for the signing key"
    try:
        if signature.get("signing_algo") != "ecdsa":
            raise ValueError("expected ecdsa")
        address = _hex_bytes(signature["signing_address"], 20)
        sig = _hex_bytes(signature["signature"], 65)
        recovered = Account.recover_message(encode_defunct(text=signature["text"]), signature="0x" + sig.hex())
        ok = compare_digest(_hex_bytes(recovered, 20), address)
        checks.append(Check("sig_valid", label, PASS if ok else FAIL))
    except (KeyError, ValueError, TypeError) as e:
        checks.append(Check("sig_valid", label, FAIL, str(e)))
        return checks

    trusted = {s.lower() for s in trusted_signers}
    checks.append(Check("sig_signer_attested", "Signing key belongs to the TEE we just attested",
                        PASS if str(signature["signing_address"]).lower() in trusted else FAIL))
    return checks


def recover_signer(text: str, signature_hex: str) -> str:
    sig = _hex_bytes(signature_hex, 65)
    return Account.recover_message(encode_defunct(text=text), signature="0x" + sig.hex())


def check_receipt_signature(receipt: dict, trusted_signers: set[str]) -> tuple[list[Check], str | None]:
    """Verify a receipt's completion signature from on-chain fields alone.

    The signed text is "{model}:{request_hash}:{response_hash}", all of which are
    on-chain, so anyone can recover the signer without the private request or answer.
    """
    text = f"{receipt['model_id']}:{receipt['request_hash']}:{receipt['response_hash']}"
    try:
        signer = recover_signer(text, receipt["completion_sig"])
    except (KeyError, ValueError, TypeError) as e:
        return [Check("sig_valid", "Completion signature is valid", FAIL, str(e))], None
    trusted = {s.lower() for s in trusted_signers}
    return [
        Check("sig_valid", "Completion signature is valid over the on-chain hashes", PASS, signer),
        Check("sig_signer_attested", "Signer is the attested TEE key in the stored report",
              PASS if signer.lower() in trusted else FAIL),
    ], signer
