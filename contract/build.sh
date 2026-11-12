#!/usr/bin/env bash
# Build the contract wasm and copy it to contract/res/ (committed, so the
# quickstart never needs Rust). Run on Linux / macOS / WSL.
#
#   Needs: rustup with wasm32-unknown-unknown, a C toolchain (build-essential),
#          and cargo-near:  cargo install cargo-near --locked
set -euo pipefail
cd "$(dirname "$0")"

TARGET="${CARGO_TARGET_DIR:-target}"

cargo test --quiet
cargo near build non-reproducible-wasm --no-abi
mkdir -p res
cp "$TARGET/near/oathbox_contract.wasm" res/oathbox_contract.wasm
sha256sum res/oathbox_contract.wasm
ls -l res/oathbox_contract.wasm
