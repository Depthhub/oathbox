import shutil

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from oathbox.hashing import digest_room
from oathbox.store import Store, changed_files
from oathbox.tamper import Tamper
from oathbox.verify import FAIL, PASS, check_receipt_signature


@pytest.fixture
def room(sample_room, tmp_path):
    dest = tmp_path / "room"
    shutil.copytree(sample_room, dest)
    return dest


def test_tamper_round_trip_restores_exact_root(room, tmp_path):
    t = Tamper(room, tmp_path / "state")
    original = digest_room(room).root
    t.enable()
    assert t.active
    assert digest_room(room).root != original
    assert not (room / "metrics.csv.orig").exists()  # backup lives outside the room
    t.enable()  # idempotent
    t.disable()
    assert not t.active
    assert digest_room(room).root == original


def test_store_attestation_and_manifest(room, tmp_path):
    s = Store(tmp_path / "state")
    h = s.put_attestation(b'{"x":1}')
    assert s.get_attestation(h) == b'{"x":1}'
    assert s.get_attestation("../../etc/passwd") is None

    before = digest_room(room)
    s.save_manifest("demo", before)
    t = Tamper(room, tmp_path / "state")
    t.enable()
    assert changed_files(s.load_manifest("demo"), digest_room(room)) == ["metrics.csv"]


def test_receipt_signature_from_onchain_fields():
    acct = Account.create()
    receipt = {"model_id": "Qwen/Qwen3.6-35B-A3B-FP8", "request_hash": "aa" * 32, "response_hash": "bb" * 32}
    text = f"{receipt['model_id']}:{receipt['request_hash']}:{receipt['response_hash']}"
    sig = acct.sign_message(encode_defunct(text=text)).signature.hex()
    receipt["completion_sig"] = sig if sig.startswith("0x") else "0x" + sig

    checks, signer = check_receipt_signature(receipt, {acct.address})
    assert signer == acct.address
    assert [c.status for c in checks] == [PASS, PASS]

    receipt["response_hash"] = "cc" * 32  # someone edits the receipt's hash
    checks, signer = check_receipt_signature(receipt, {acct.address})
    assert signer != acct.address
    assert checks[1].status == FAIL
