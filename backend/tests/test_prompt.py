import json

import pytest

from oathbox.hashing import digest_room, read_room
from oathbox.prompt import SYSTEM_PROMPT, build_request_body

MODEL = "example/tee-model"


def test_body_is_deterministic(sample_room):
    files = read_room(sample_room)
    a = build_request_body(MODEL, files, "Is MRR growing?")
    b = build_request_body(MODEL, list(reversed(files)), "Is MRR growing?")
    assert a == b


def test_body_is_canonical_json(sample_room):
    body = build_request_body(MODEL, read_room(sample_room), "Is MRR growing?")
    parsed = json.loads(body)
    assert body == json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert parsed["stream"] is False
    assert parsed["model"] == MODEL
    assert parsed["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}


def test_body_binds_root_and_question(sample_room):
    root = digest_room(sample_room).root
    body = build_request_body(MODEL, read_room(sample_room), "  Who owns more than 10%?  ")
    user = json.loads(body)["messages"][1]["content"]
    assert f"DATA ROOM ROOT (sha256): {root}" in user
    assert user.endswith("QUESTION: Who owns more than 10%?")
    assert "=== repo/ledgerlight/config.py ===" in user


def test_question_or_room_change_changes_bytes(sample_room):
    files = read_room(sample_room)
    base = build_request_body(MODEL, files, "Is MRR growing?")
    assert build_request_body(MODEL, files, "Is MRR shrinking?") != base
    changed = [(r, d + b"#" if r == "metrics.csv" else d) for r, d in files]
    assert build_request_body(MODEL, changed, "Is MRR growing?") != base


def test_rejects_empty_inputs(sample_room):
    with pytest.raises(ValueError):
        build_request_body("", read_room(sample_room), "q")
    with pytest.raises(ValueError):
        build_request_body(MODEL, read_room(sample_room), "   ")


def test_room_fits_in_one_prompt(sample_room):
    # Rough budget check: ~4 chars/token, keep the whole request under ~12k tokens.
    body = build_request_body(MODEL, read_room(sample_room), "Is MRR growing?")
    assert len(body) < 48_000
