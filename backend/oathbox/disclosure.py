"""Post-filter that runs on every model answer before it is shown or receipted.

Two rules (either one rejects the answer):

1. Verbatim overlap with any data-room file, whitespace collapsed on both
   sides first (so re-indented or re-wrapped code is still caught). The limit
   depends on what KIND of file the text comes from:
   - data files (.csv, .json, .yaml, .env, ...): any >= 40-character run;
   - code files (.py, .js, ...): >= 40-character runs that look like code
     (code symbols or digit/comma runs), so a short everyday phrase shared
     with a comment ("to environment variables before the audit") is fine;
   - documents (.md, .txt, ...): only fenced ``` code blocks get the 40 limit.
     Prose is judged by file type, not by symbols: a pitch deck is full of
     "$2.5M" and "78%" and is still prose;
   - every file: >= 120 characters of any text (about one long sentence).
     Restating one sentence of a pitch is fine; copying paragraphs is not.
2. Secrets: any secret-looking string found in the room (or any 12-character
   window of it) appears in the answer. Rule 1 alone misses short keys.

On rejection the caller returns "Answer withheld by disclosure filter" and
records nothing on-chain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_OVERLAP = 40           # code / data
MIN_PROSE_OVERLAP = 120    # any text, including prose documents
SECRET_WINDOW = 12
_CODE_CHARS = set("=(){}[]<>;:_\"`/\\|#*$@&%+~^")
_DATA_RUN = re.compile(r"\d,|,\d")
WITHHELD_MESSAGE = "Answer withheld by disclosure filter."

_WS = re.compile(r"\s+")
_FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)

DOC_EXTS = {".md", ".markdown", ".txt", ".rst", ".adoc"}
DATA_EXTS = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".yaml", ".yml", ".toml",
             ".ini", ".cfg", ".conf", ".env", ".xml", ".sql", ".lock"}


def file_kind(path: str) -> str:
    """'doc', 'data' or 'code', from the file name alone."""
    name = path.rsplit("/", 1)[-1].lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if name.startswith(".env") or ext in DATA_EXTS:
        return "data"
    if ext in DOC_EXTS and not name.startswith("requirements"):
        return "doc"
    return "code"

_SECRET_PATTERNS = [
    # NAME = "value" style assignments of key-ish names
    re.compile(
        r"""(?i)(?:api[_-]?key|secret|token|passw(?:or)?d|private[_-]?key|access[_-]?key)\w*\s*[:=]\s*["']([^"'\s]{12,})["']"""
    ),
    # Well-known token shapes
    re.compile(r"\b((?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,})"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,})\b"),
    re.compile(r"\b(xox[abprs]-[A-Za-z0-9-]{10,})\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def _collapse(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _looks_like_code_or_data(s: str) -> bool:
    return any(ch in _CODE_CHARS for ch in s) or bool(_DATA_RUN.search(s))


def find_secrets(text: str) -> set[str]:
    found: set[str] = set()
    for pat in _SECRET_PATTERNS:
        for m in pat.finditer(text):
            found.add(m.group(1) if m.groups() else m.group(0))
    return found


@dataclass(frozen=True)
class FilterResult:
    allowed: bool
    reason: str | None = None   # never contains the matched content itself


class DisclosureFilter:
    def __init__(self, files: list[tuple[str, bytes]]):
        self._code_grams: set[str] = set()    # 40-char runs that look like code/data
        self._prose_grams: set[str] = set()   # every 64-char run
        self._secret_windows: set[str] = set()
        self.secret_count = 0
        for path, data in files:
            text = data.decode("utf-8", errors="ignore")
            collapsed = _collapse(text)
            kind = file_kind(path)
            if kind == "data":
                strict = [(collapsed, False)]                 # every run counts
            elif kind == "code":
                strict = [(collapsed, True)]                  # code-looking runs only
            else:
                strict = [(_collapse(m.group(0)), True) for m in _FENCE.finditer(text)]
            for chunk, only_code_like in strict:
                for i in range(len(chunk) - MIN_OVERLAP + 1):
                    gram = chunk[i : i + MIN_OVERLAP]
                    if not only_code_like or _looks_like_code_or_data(gram):
                        self._code_grams.add(gram)
            for i in range(len(collapsed) - MIN_PROSE_OVERLAP + 1):
                self._prose_grams.add(collapsed[i : i + MIN_PROSE_OVERLAP])
            for secret in find_secrets(text):
                self.secret_count += 1
                if len(secret) <= SECRET_WINDOW:
                    self._secret_windows.add(secret)
                else:
                    for i in range(len(secret) - SECRET_WINDOW + 1):
                        self._secret_windows.add(secret[i : i + SECRET_WINDOW])

    def check(self, answer: str) -> FilterResult:
        for w in self._secret_windows:
            if w in answer:
                return FilterResult(False, "answer contains a secret from the data room")
        collapsed = _collapse(answer)
        for i in range(len(collapsed) - MIN_OVERLAP + 1):
            if collapsed[i : i + MIN_OVERLAP] in self._code_grams:
                return FilterResult(
                    False, f"answer repeats {MIN_OVERLAP}+ characters of code or data verbatim from the data room"
                )
        for i in range(len(collapsed) - MIN_PROSE_OVERLAP + 1):
            if collapsed[i : i + MIN_PROSE_OVERLAP] in self._prose_grams:
                return FilterResult(
                    False, f"answer repeats {MIN_PROSE_OVERLAP}+ characters verbatim from the data room"
                )
        return FilterResult(True)
