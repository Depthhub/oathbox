"""Deploy the Oathbox contract to NEAR testnet.

    backend/.venv/Scripts/python scripts/deploy_contract.py            # dry run: shows the plan
    backend/.venv/Scripts/python scripts/deploy_contract.py --yes      # sends the transaction

Reads NEAR_ACCOUNT_ID / NEAR_PRIVATE_KEY (your funded testnet account) from .env.
CONTRACT_ID defaults to oathbox.<NEAR_ACCOUNT_ID>.

First deploy: one atomic transaction that creates CONTRACT_ID as a subaccount,
funds it (storage), adds your key, deploys the wasm and calls `new`.
Later deploys: replace the code only (state is kept).

No Rust needed: uses the prebuilt contract/res/oathbox_contract.wasm.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import near
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
WASM = REPO / "contract" / "res" / "oathbox_contract.wasm"
# Contract code storage: 170 KB x 1e19 yocto/byte ~= 1.70 NEAR. 1.8 leaves a small margin
# and fits the 2 NEAR testnet faucet limit. Override with DEPLOY_FUNDING="3 NEAR".
FUNDING = os.getenv("DEPLOY_FUNDING", "1.8 NEAR")
EXPLORER = "https://testnet.nearblocks.io/txns/"


def main() -> int:
    load_dotenv(REPO / ".env")
    account = os.getenv("NEAR_ACCOUNT_ID", "").strip()
    key = os.getenv("NEAR_PRIVATE_KEY", "").strip()
    if not account or not key:
        print("Set NEAR_ACCOUNT_ID and NEAR_PRIVATE_KEY in .env first.")
        return 2
    if not account.endswith(".testnet"):
        print(f"Refusing: {account} is not a testnet account.")
        return 2
    contract = os.getenv("CONTRACT_ID", "").strip() or f"oathbox.{account}"
    if not contract.endswith("." + account) and contract != account:
        print(f"CONTRACT_ID must be a subaccount of {account} (got {contract}).")
        return 2
    if not WASM.exists():
        print(f"Missing {WASM.relative_to(REPO)}. Build it first: contract/build.sh (in WSL).")
        return 2

    code = WASM.read_bytes()
    client = near.Near(network="testnet", account_id=account, private_key=key)
    balance = client.balance(account)
    exists = client.account_exists(contract)

    print(f"signer      : {account} (balance {balance})")
    print(f"contract    : {contract} ({'exists: code will be replaced, state kept' if exists else 'new'})")
    print(f"wasm        : {WASM.relative_to(REPO)}  {len(code)} bytes  sha256 {hashlib.sha256(code).hexdigest()}")
    if not exists:
        print(f"funding     : {FUNDING} moved from {account} to {contract} for storage")
        have = float(str(balance).split()[0])
        need = float(FUNDING.split()[0]) + 0.1
        if have < need:
            print(f"\nNot enough testnet NEAR: have {have:g}, need ~{need:.2f} (funding + gas).")
            print("Top up for free at https://near-faucet.io, then run this again.")
            return 2
    if "--yes" not in sys.argv:
        print("\nDry run. Re-run with --yes to send the transaction.")
        return 0

    if exists:
        result = client.send_transaction(contract, [near.deploy_contract(code)])
    else:
        public_key = near.parse_key(key).public_key
        result = client.send_transaction(
            contract,
            [
                near.create_account(),
                near.transfer(FUNDING),
                near.add_full_access_key(public_key),
                near.deploy_contract(code),
                near.function_call("new", {}, gas="30 Tgas"),
            ],
        )
    tx = result.transaction_hash
    print(f"\ndeployed    : {contract}\ntransaction : {EXPLORER}{tx}")
    print(f"\nSet CONTRACT_ID={contract} in .env if it is not already.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
