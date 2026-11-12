"""System prompt and the deterministic chat-request builder.

The request body is built here, byte for byte, and those exact bytes are what
we POST to the TEE and hash into request_hash. Because the builder is pure and
deterministic, the founder can later rebuild the same bytes from
(data room, question) and recompute request_hash without the server keeping
any copy of the request.
"""

from __future__ import annotations

import json

from .hashing import DataRoomDigest, digest_files

# Shown read-only on the founder page (story F4).
DISCLOSURE_RULES: tuple[str, ...] = (
    "Answer only from the provided data room. If the answer is not in it, say "
    "\"Not determinable from the data room.\"",
    "Never output raw source code, configuration values, or file contents. Never quote "
    "any text from the files, including code comments, READMEs and TODOs; always "
    "paraphrase in your own short words.",
    "Never output secrets, keys, tokens, or passwords. You may say that one exists "
    "and name the file it is in.",
    "Never output personal names or full rows of customer data. Use roles, counts, "
    "aggregates, and ranges instead.",
    "Prefer yes/no, aggregates, trends, and percentages. Cite file names, not contents.",
    "Keep the answer under 120 words.",
)

SYSTEM_PROMPT = (
    "You are Oathbox, a due-diligence assistant running inside a trusted execution "
    "environment. An investor is asking questions about a startup's private data room. "
    "The investor must learn facts, never the underlying files.\n\nRules:\n"
    + "\n".join(f"{i}. {rule}" for i, rule in enumerate(DISCLOSURE_RULES, start=1))
)

MAX_TOKENS = 600
TEMPERATURE = 0


def _render_file(rel: str, data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return f"=== {rel} ===\n[binary file, {len(data)} bytes, contents omitted]\n"
    return f"=== {rel} ===\n{text}\n" if not text.endswith("\n") else f"=== {rel} ===\n{text}"


def build_user_message(
    files: list[tuple[str, bytes]], question: str, digest: DataRoomDigest | None = None
) -> str:
    digest = digest or digest_files(files)
    ordered = sorted(files, key=lambda t: t[0].encode("utf-8"))
    manifest = "\n".join(f"- {f.path} ({f.size} bytes, sha256 {f.sha256})" for f in digest.files)
    body = "".join(_render_file(rel, data) for rel, data in ordered)
    return (
        f"DATA ROOM ROOT (sha256): {digest.root}\n"
        f"FILES ({digest.file_count}):\n{manifest}\n\n"
        f"--- BEGIN DATA ROOM ---\n{body}--- END DATA ROOM ---\n\n"
        f"QUESTION: {question.strip()}"
    )


def build_request_body(model: str, files: list[tuple[str, bytes]], question: str) -> bytes:
    """Canonical JSON bytes for POST /v1/chat/completions (non-streaming)."""
    if not model:
        raise ValueError("model is required")
    if not question.strip():
        raise ValueError("question is empty")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(files, question)},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "stream": False,
        # No hidden reasoning: it would burn the token budget and, worse, the raw
        # response (which the investor keeps for verification) would carry
        # unfiltered reasoning over the private files.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
