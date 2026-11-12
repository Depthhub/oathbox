"""One investor question, end to end (minus the chain calls, which the API layer adds).

Order follows the docs' preflight rule: attest first, then ask, then match the
answer's signer to a signer we verified *before* the completion.

    1. fresh nonce -> attestation report -> verify every model candidate
    2. exact-bytes chat completion
    3. completion signature -> check it against the exchange and the attested signers
    4. disclosure post-filter

Nothing here writes to disk. The caller gets the bytes it needs for the public
attestation store and the investor's receipt bundle, then drops the rest.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from .disclosure import WITHHELD_MESSAGE, DisclosureFilter
from .prompt import build_request_body
from .tee import NearAICloud, TEEError, answer_text
from .verify import Check, FAIL, ModelVerdict, badge, check_model_report, check_signature, sha256_hex


@dataclass
class AskOutcome:
    delivered: bool                 # False when the disclosure filter withheld the answer
    answer: str                     # the answer, or WITHHELD_MESSAGE
    model: str
    nonce: str
    chat_id: str
    question_hash: str
    answer_hash: str
    request_hash: str
    response_hash: str
    attestation_hash: str
    signature: dict
    checks: list[Check]
    usage: dict = field(default_factory=dict)
    filter_reason: str | None = None
    # bytes handed back to the caller, never stored by this module
    attestation_bytes: bytes = b""
    response_bytes: bytes = b""
    raw_answer: str = ""            # unfiltered; only for local debugging of fictional data, never sent anywhere

    @property
    def badge(self) -> str:
        return badge(self.checks)


async def ask(
    cloud: NearAICloud, files: list[tuple[str, bytes]], question: str, model: str
) -> AskOutcome:
    # 1. preflight attestation
    nonce = secrets.token_hex(32)
    att_bytes, report = await cloud.attestation(model, nonce)
    candidates = report.get("model_attestations") or []
    if not candidates:
        raise TEEError("no model attestation returned for this model; refusing to ask")
    verdicts: list[ModelVerdict] = [await check_model_report(c, nonce, cloud.http) for c in candidates]
    trusted = {v.signing_address.lower() for v in verdicts if v.signer_trusted}

    # 2. exact-bytes completion
    body = build_request_body(model, files, question)
    resp_bytes, resp = await cloud.chat(body)
    chat_id = str(resp.get("id", ""))
    answer = answer_text(resp)

    # 3. signature, matched to the preflight signers
    signature = await cloud.signature(chat_id, model)
    sig_checks = check_signature(
        signature, model=model, request_bytes=body, response_bytes=resp_bytes, trusted_signers=trusted
    )
    signer = str(signature.get("signing_address", "")).lower()
    match = next((v for v in verdicts if v.signing_address.lower() == signer), None)
    att_checks = match.checks if match else verdicts[0].checks
    checks = list(att_checks) + sig_checks
    if match is None:
        checks.append(Check("signer_in_report", "Answer's signer appears in the attestation report", FAIL))

    # 4. disclosure filter
    result = DisclosureFilter(files).check(answer)
    delivered = result.allowed and bool(answer)
    shown = answer if delivered else WITHHELD_MESSAGE

    return AskOutcome(
        delivered=delivered,
        answer=shown,
        model=model,
        nonce=nonce,
        chat_id=chat_id,
        question_hash=sha256_hex(question.strip().encode("utf-8")),
        answer_hash=sha256_hex(answer.encode("utf-8")),
        request_hash=sha256_hex(body),
        response_hash=sha256_hex(resp_bytes),
        attestation_hash=sha256_hex(att_bytes),
        signature=signature,
        checks=checks,
        usage=resp.get("usage") or {},
        filter_reason=None if delivered else (result.reason or "model returned no answer"),
        attestation_bytes=att_bytes,
        response_bytes=resp_bytes,
        raw_answer=answer,
    )
