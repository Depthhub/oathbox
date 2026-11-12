"""Thin client for the Oathbox contract on NEAR, via near-kit.

near-kit is synchronous; the API layer runs these calls in a worker thread and
serialises writes so transaction nonces never race.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import near

# Each write attaches a deposit; the contract keeps the exact storage cost and refunds the rest.
COMMIT_DEPOSIT = "0.05 NEAR"
RECEIPT_DEPOSIT = "0.03 NEAR"
WRITE_GAS = "50 Tgas"

EXPLORERS = {
    "testnet": "https://testnet.nearblocks.io",
    "mainnet": "https://nearblocks.io",
}


class ChainError(RuntimeError):
    pass


def _decode_return(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        for candidate in (value, _b64(value)):
            if candidate is None:
                continue
            try:
                return json.loads(candidate)
            except (ValueError, TypeError):
                pass
    return value


def _b64(value: str) -> str | None:
    try:
        return base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


class OathboxChain:
    def __init__(
        self,
        contract_id: str,
        account_id: str | None = None,
        private_key: str | None = None,
        network: str = "testnet",
        rpc_url: str | None = None,
    ):
        if not contract_id:
            raise ChainError("CONTRACT_ID is not set")
        self.contract_id = contract_id
        self.network = network
        self.account_id = account_id
        kw = {"rpc_url": rpc_url} if rpc_url else {}
        self._view = near.Near(network=network, **kw)
        self._signer = (
            near.Near(network=network, account_id=account_id, private_key=private_key, **kw)
            if account_id and private_key
            else None
        )

    # ---------- links ----------
    def tx_url(self, tx_hash: str) -> str:
        return f"{EXPLORERS.get(self.network, EXPLORERS['testnet'])}/txns/{tx_hash}"

    def account_url(self, account: str | None = None) -> str:
        return f"{EXPLORERS.get(self.network, EXPLORERS['testnet'])}/address/{account or self.contract_id}"

    # ---------- views ----------
    def _call_view(self, method: str, args: dict) -> Any:
        try:
            return self._view.view(self.contract_id, method, args)
        except near.NearError as e:
            raise ChainError(f"view {method} failed: {e}") from e

    def get_dataroom(self, room_id: str) -> dict | None:
        return self._call_view("get_dataroom", {"id": room_id})

    def get_receipt(self, receipt_id: int) -> dict | None:
        return self._call_view("get_receipt", {"id": int(receipt_id)})

    def get_receipts(self, room_id: str, from_index: int = 0, limit: int = 50) -> list[dict]:
        return self._call_view(
            "get_receipts", {"dataroom_id": room_id, "from_index": from_index, "limit": limit}
        ) or []

    def get_backends(self, room_id: str) -> list[str]:
        return self._call_view("get_backends", {"dataroom_id": room_id}) or []

    def is_full_access_key(self, account_id: str, public_key: str) -> bool:
        """True only if public_key is a FullAccess key of account_id on chain."""
        try:
            key = self._view.access_key(account_id, public_key)
        except (near.AccessKeyNotFoundError, near.AccountNotFoundError, near.InvalidKeyError):
            return False
        except near.NearError as e:
            raise ChainError(f"access key lookup failed: {e}") from e
        return str(key.permission) == "FullAccess"

    # ---------- writes ----------
    def _call(self, method: str, args: dict, deposit: str) -> tuple[Any, str]:
        if self._signer is None:
            raise ChainError("NEAR_ACCOUNT_ID / NEAR_PRIVATE_KEY are not set; cannot write")
        try:
            res = self._signer.call(self.contract_id, method, args, gas=WRITE_GAS, deposit=deposit)
        except near.ContractPanicError as e:
            raise ChainError(f"contract rejected {method}: {e}") from e
        except near.NearError as e:
            raise ChainError(f"{method} failed: {e}") from e
        return _decode_return(res.success_value), res.transaction_hash

    def commit_dataroom(self, room_id: str, root_hash: str, file_count: int) -> tuple[dict, str]:
        return self._call(
            "commit_dataroom",
            {"id": room_id, "root_hash": root_hash, "file_count": int(file_count)},
            COMMIT_DEPOSIT,
        )

    def record_receipt(
        self,
        *,
        dataroom_id: str,
        dataroom_root: str,
        question_hash: str,
        answer_hash: str,
        request_hash: str,
        response_hash: str,
        completion_sig: str,
        model_id: str,
        attestation_hash: str,
        nonce: str,
        attestation_checked_offchain: bool,
    ) -> tuple[int, str]:
        value, tx = self._call(
            "record_receipt",
            {
                "dataroom_id": dataroom_id,
                "dataroom_root": dataroom_root,
                "question_hash": question_hash,
                "answer_hash": answer_hash,
                "request_hash": request_hash,
                "response_hash": response_hash,
                "completion_sig": completion_sig,
                "model_id": model_id,
                "attestation_hash": attestation_hash,
                "nonce": nonce,
                "attestation_checked_offchain": bool(attestation_checked_offchain),
            },
            RECEIPT_DEPOSIT,
        )
        return int(value), tx
