from oathbox.disclosure import DisclosureFilter, file_kind, find_secrets
from oathbox.hashing import read_room

FAKE_KEY = "llpay_demo_7Q2mX9vKc4RtW8nZ3bYh6JdP"


def make_filter(sample_room):
    return DisclosureFilter(read_room(sample_room))


def test_sample_room_secret_is_detected(sample_room):
    f = make_filter(sample_room)
    assert f.secret_count >= 1


def test_safe_answers_pass(sample_room):
    f = make_filter(sample_room)
    for answer in [
        "Yes. MRR grew in 11 of 12 months, from about $18k to about $48k; the only dip was May 2026.",
        "Yes: one hardcoded payment API key in repo/ledgerlight/config.py. Move it to an env variable.",
        "Four holders exceed 10%: the CEO (38%), the CTO (27%), the lead seed fund (15%) and the option pool (12%).",
        "Not determinable from the data room.",
    ]:
        assert f.check(answer).allowed, answer


def test_full_key_blocked(sample_room):
    f = make_filter(sample_room)
    r = f.check(f"The key is {FAKE_KEY}.")
    assert not r.allowed
    assert FAKE_KEY not in (r.reason or "")


def test_partial_key_blocked(sample_room):
    f = make_filter(sample_room)
    assert not f.check(f"It starts with {FAKE_KEY[:14]}...").allowed


def test_verbatim_code_blocked_even_if_reindented(sample_room):
    f = make_filter(sample_room)
    leaked = (
        "Here is the logic:\n"
        "subtotal = sum((item.subtotal for item in invoice.items),\n        Decimal(\"0\"))"
    )
    assert not f.check(leaked).allowed


def test_verbatim_csv_rows_blocked(sample_room):
    f = make_filter(sample_room)
    assert not f.check("Rows: 2026-09,43600,19,3,169,1.8\n2026-10,47950,21,4,186,2.2").allowed


def test_short_prose_phrase_from_a_comment_passes(sample_room):
    # Real model output from the smoke test: paraphrases the TODO comment and shares
    # a ~49-char everyday phrase with it. That's a paraphrase, not a leak.
    f = make_filter(sample_room)
    answer = (
        "Yes, there is a hardcoded secret. The file `repo/ledgerlight/config.py` contains a hardcoded "
        "API key for the payments provider, stored in the variable `PAYMENTS_API_KEY`. The code comments "
        "note that secrets should be moved to environment variables before the SOC 2 audit."
    )
    assert f.check(answer).allowed


def test_long_copied_prose_blocked(sample_room):
    f = make_filter(sample_room)
    copied = (
        "The company is an invented B2B invoicing startup used to demo Oathbox. "
        "Every name, number, customer and key in this folder is made up."
    )
    r = f.check(copied)
    assert not r.allowed
    assert "120+" in (r.reason or "")


# A pitch-style room: prose full of "$" and "%" must be judged as prose, while code,
# data rows, fenced code in docs, copied paragraphs and secrets stay blocked.
PITCH = {
    "README.md": (
        "# Acme\n\nKettlebird is inventory and supplier ordering software for independent coffee shops.\n"
        "We are raising $2.5M on a post-money SAFE.\n"
    ),
    "pitch.md": (
        "## Traction\n- $64.8K MRR, up from $21.3K in November 2025 (3.0x in 11 months).\n"
        "Raising $2.5M on a post-money SAFE with a $14M valuation cap.\n\n"
        "Independent coffee shops track stock on whiteboards and in group chats. The average shop runs out "
        "of a key item 3.1 times a month, and each stock-out costs an estimated $180-$420 in lost sales.\n\n"
        "```\nexport POS_WEBHOOK_URL=https://hooks.example.invalid/pos/ingest\n```\n"
    ),
    "customers.csv": "customer_id,segment,region,plan\nC-0002,Multi-location chain,US-Northeast,Multi-location\n",
    "app/config.py": (
        'POS_API_TOKEN = "pos_live_9fK2mQ7xL4vR8tZ1"\n'
        'MAX_RETRIES_FOR_SUPPLIER_EMAIL = int(os.environ.get("RETRIES", "5"))\n'
    ),
}


def pitch_filter():
    return DisclosureFilter([(p, t.encode()) for p, t in PITCH.items()])


def test_pitch_sentences_with_money_and_percent_pass():
    f = pitch_filter()
    for answer in [
        "Kettlebird is inventory and supplier ordering software for independent coffee shops.",
        "They are raising $2.5M on a post-money SAFE with a $14M valuation cap.",
        "Traction: $64.8K MRR, up from $21.3K in November 2025 (3.0x in 11 months).",
    ]:
        assert f.check(answer).allowed, answer


def test_pitch_room_still_blocks_leaks():
    f = pitch_filter()
    # a copied paragraph (over 120 characters)
    assert not f.check(
        "Independent coffee shops track stock on whiteboards and in group chats. The average shop runs out "
        "of a key item 3.1 times a month."
    ).allowed
    # fenced code inside a document keeps the strict code limit
    assert not f.check("Set POS_WEBHOOK_URL=https://hooks.example.invalid/pos/ingest").allowed
    # data rows: every 40-character run counts, even without digits
    assert not f.check("The row is C-0002,Multi-location chain,US-Northeast,Multi-location").allowed
    # code
    assert not f.check('They set MAX_RETRIES_FOR_SUPPLIER_EMAIL = int(os.environ.get("RETRIES", "5"))').allowed
    # secrets, whole or partial
    assert not f.check("The token starts pos_live_9fK2mQ").allowed


def test_file_kind():
    assert file_kind("01-pitch/deck.md") == "doc"
    assert file_kind("notes.TXT") == "doc"
    assert file_kind("requirements.txt") == "code"
    assert file_kind("data/metrics.csv") == "data"
    assert file_kind(".env.local") == "data"
    assert file_kind("repo/app.py") == "code"
    assert file_kind("Dockerfile") == "code"


def test_find_secrets_patterns():
    text = 'AWS = "AKIAABCDEFGHIJKLMNOP"\ntoken: "ghp_' + "a" * 36 + '"\npassword = "hunter2hunter2"'
    found = find_secrets(text)
    assert "AKIAABCDEFGHIJKLMNOP" in found
    assert "hunter2hunter2" in found
    assert any(s.startswith("ghp_") for s in found)
