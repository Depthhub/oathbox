"""Offline tests for completion-signature checks, using a throwaway local key."""

from eth_account import Account
from eth_account.messages import encode_defunct

from oathbox.verify import FAIL, PASS, Check, badge, check_signature, replay_rtmr3, signature_text

MODEL = "Qwen/Qwen3.6-35B-A3B-FP8"
REQ = b'{"model":"x","messages":[]}'
RESP = b'{"id":"chatcmpl-1","choices":[]}'


def signed(text: str, acct=None, kind="provider_tee") -> tuple[dict, str]:
    acct = acct or Account.create()
    sig = acct.sign_message(encode_defunct(text=text)).signature.hex()
    return (
        {
            "text": text,
            "signature": sig if sig.startswith("0x") else "0x" + sig,
            "signing_address": acct.address,
            "signing_algo": "ecdsa",
            "signature_kind": kind,
        },
        acct.address,
    )


def statuses(checks):
    return {c.id: c.status for c in checks}


def test_valid_signature_from_attested_signer_passes():
    sig, addr = signed(signature_text(MODEL, REQ, RESP))
    checks = check_signature(sig, model=MODEL, request_bytes=REQ, response_bytes=RESP, trusted_signers={addr})
    assert set(statuses(checks).values()) == {PASS}
    assert badge(checks) == "verified"


def test_tampered_answer_fails():
    sig, addr = signed(signature_text(MODEL, REQ, RESP))
    checks = check_signature(
        sig, model=MODEL, request_bytes=REQ, response_bytes=RESP.replace(b"1", b"2"), trusted_signers={addr}
    )
    assert statuses(checks)["sig_covers_exchange"] == FAIL
    assert badge(checks) == "failed"


def test_signer_not_in_attestation_fails():
    sig, _ = signed(signature_text(MODEL, REQ, RESP))
    checks = check_signature(sig, model=MODEL, request_bytes=REQ, response_bytes=RESP, trusted_signers={"0x" + "11" * 20})
    assert statuses(checks)["sig_signer_attested"] == FAIL


def test_forged_address_fails():
    sig, _ = signed(signature_text(MODEL, REQ, RESP))
    other = Account.create().address
    sig["signing_address"] = other
    checks = check_signature(sig, model=MODEL, request_bytes=REQ, response_bytes=RESP, trusted_signers={other})
    assert statuses(checks)["sig_valid"] == FAIL


def test_gateway_signature_rejected():
    sig, addr = signed(signature_text(MODEL, REQ, RESP), kind="gateway")
    checks = check_signature(sig, model=MODEL, request_bytes=REQ, response_bytes=RESP, trusted_signers={addr})
    assert statuses(checks)["sig_kind"] == FAIL


def test_badge_never_verified_with_error_or_skip():
    assert badge([Check("a", "", PASS), Check("b", "", "error")]) == "attestation_fetched"
    assert badge([Check("a", "", PASS), Check("b", "", "skip")]) == "attestation_fetched"
    assert badge([Check("a", "", "warn")]) == "verified_with_warnings"


def test_rtmr3_replay_empty_log():
    assert replay_rtmr3("[]") == bytes(48)
