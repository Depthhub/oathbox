"""Founder sign-in with a NEAR wallet (NEP-413 signed message).

1. GET  /api/auth/challenge  -> a fresh 32-byte nonce (single use, 5 minutes)
2. The wallet signs {message, recipient, nonce} off-chain (no transaction, no fee).
3. POST /api/auth/verify     -> we check the signature AND that the key is a
   FullAccess key of that account on NEAR, then issue a session token.

The token is an HMAC over {account, expiry}; the server keeps no session table.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

import near

MESSAGE = "Sign in to Oathbox to manage your data rooms. This does not send a transaction."
RECIPIENT = "oathbox"
CHALLENGE_TTL_S = 300
SESSION_TTL_S = 12 * 3600


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class AuthError(Exception):
    pass


class Auth:
    def __init__(self, state_dir: Path, secret: str | None = None):
        self._challenges: dict[str, float] = {}
        if secret:
            self._key = secret.encode()
        else:
            path = Path(state_dir) / "session.key"
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(secrets.token_hex(32), encoding="ascii")
            self._key = path.read_text(encoding="ascii").strip().encode()

    # ---------- challenge ----------
    def challenge(self) -> dict:
        now = time.time()
        self._challenges = {n: t for n, t in self._challenges.items() if t > now}
        nonce = near.generate_nonce()
        b64 = base64.b64encode(nonce).decode("ascii")
        self._challenges[b64] = now + CHALLENGE_TTL_S
        return {"message": MESSAGE, "recipient": RECIPIENT, "nonce": b64}

    def verify(self, *, account_id: str, public_key: str, signature: str, nonce: str,
               callback_url: str | None, is_full_access_key) -> str:
        """Check the signed challenge and return a session token, or raise AuthError."""
        expiry = self._challenges.pop(nonce, None)  # single use
        if expiry is None or expiry < time.time():
            raise AuthError("That sign-in request expired. Try again.")
        try:
            raw_nonce = base64.b64decode(nonce)
        except ValueError as e:
            raise AuthError("Malformed nonce.") from e
        signed = near.SignedMessage(account_id=account_id, public_key=public_key, signature=signature)
        # Wallets differ on whether callbackUrl is part of the signed payload; accept either.
        ok = any(
            near.verify_message(signed, MESSAGE, RECIPIENT, raw_nonce, cb, max_age_ms=None)
            for cb in dict.fromkeys([None, callback_url or None])
        )
        if not ok:
            raise AuthError("The wallet signature didn't check out.")
        if not is_full_access_key(account_id, public_key):
            raise AuthError(f"That key doesn't control {account_id}.")
        return self.issue(account_id)

    # ---------- session tokens ----------
    def issue(self, account_id: str, ttl: int = SESSION_TTL_S) -> str:
        body = _b64u(json.dumps({"a": account_id, "e": int(time.time()) + ttl}, separators=(",", ":")).encode())
        sig = _b64u(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
        return f"{body}.{sig}"

    def account_for(self, token: str | None) -> str | None:
        if not token or "." not in token:
            return None
        body, sig = token.rsplit(".", 1)
        want = _b64u(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, want):
            return None
        try:
            data = json.loads(_unb64u(body))
        except ValueError:
            return None
        if int(data.get("e", 0)) < time.time():
            return None
        return data.get("a") or None


def new_secret() -> str:
    return os.urandom(32).hex()
