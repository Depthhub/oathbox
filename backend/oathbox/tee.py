"""NEAR AI Cloud client: attestation report, exact-bytes chat, completion signature.

Endpoints and fields follow https://docs.near.ai/cloud/verification/cloud-api.
The chat request is POSTed as the exact bytes built by prompt.build_request_body,
and the exact response bytes are kept, because the completion signature covers
sha256(request bytes) and sha256(response bytes).
"""

from __future__ import annotations

import asyncio
import json

import httpx

DEFAULT_BASE_URL = "https://cloud-api.near.ai"

# Only NEAR-operated TEE models ("owned_by": "nearai" in /v1/models).
# Third-party ("attested 3p") and provider models (OpenAI, Anthropic, Google...)
# run outside NEAR's TEE fleet and would break the privacy claim.
TEE_MODEL_ALLOWLIST = frozenset(
    {
        "Qwen/Qwen3.6-35B-A3B-FP8",
        "deepseek-ai/DeepSeek-V4.1-Flash-1017",
    }
)


class TEEError(RuntimeError):
    pass


class NearAICloud:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, http: httpx.AsyncClient | None = None):
        if not api_key:
            raise TEEError("NEARAI_API_KEY is not set")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0))

    @property
    def http(self) -> httpx.AsyncClient:
        return self._http

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self, **extra: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "Accept": "application/json", **extra}

    async def attestation(self, model: str, nonce_hex: str) -> tuple[bytes, dict]:
        """GET /v1/attestation/report for a NEAR-hosted model, bound to our nonce."""
        _require_allowed(model)
        if len(nonce_hex) != 64:
            raise ValueError("nonce must be 32 bytes as 64 hex chars")
        r = await self._http.get(
            f"{self._base}/v1/attestation/report",
            params={"signing_algo": "ecdsa", "nonce": nonce_hex, "model": model, "provider": "near"},
            headers=self._headers(**{"x-no-aliasing": "true"}),
        )
        if r.status_code != 200:
            raise TEEError(f"attestation report failed: HTTP {r.status_code}")
        return r.content, r.json()

    async def chat(self, body: bytes) -> tuple[bytes, dict]:
        """POST the exact request bytes; return the exact (uncompressed) response bytes."""
        model = json.loads(body).get("model", "")
        _require_allowed(model)
        r = await self._http.post(
            f"{self._base}/v1/chat/completions",
            content=body,
            headers=self._headers(
                **{
                    "Content-Type": "application/json",
                    "x-no-aliasing": "true",
                    "Accept-Encoding": "identity",
                }
            ),
        )
        if r.status_code != 200:
            raise TEEError(f"chat completion failed: HTTP {r.status_code}: {r.text[:300]}")
        return r.content, r.json()

    async def signature(self, chat_id: str, model: str, attempts: int = 6, delay: float = 1.0) -> dict:
        """GET /v1/signature/{chat_id}. 404 right after a completion is normal; retry briefly."""
        last = ""
        for i in range(attempts):
            r = await self._http.get(
                f"{self._base}/v1/signature/{chat_id}",
                params={"model": model, "signing_algo": "ecdsa"},
                headers=self._headers(),
            )
            if r.status_code == 200:
                data = r.json()
                if "error_code" not in data:
                    return data
                last = f"unavailable: {data.get('error_code')}"
            else:
                last = f"HTTP {r.status_code}"
            if i + 1 < attempts:
                await asyncio.sleep(delay)
        raise TEEError(f"completion signature not available ({last})")


def _require_allowed(model: str) -> None:
    if model not in TEE_MODEL_ALLOWLIST:
        raise TEEError(f"model {model!r} is not on the NEAR TEE allow-list")


def answer_text(response: dict) -> str:
    try:
        return (response["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise TEEError("unexpected chat response shape") from e
