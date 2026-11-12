# Oathbox — macOS / Linux / WSL. On Windows PowerShell use scripts\install.ps1 and scripts\demo.ps1.
PY   ?= python3
VENV := backend/.venv
BIN  := $(VENV)/bin

.PHONY: install test demo e2e contract

install:            ## Python venv + backend, then build the web app
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e "backend[dev]"
	cd web && npm ci && npm run build
	@test -f .env || (cp .env.example .env && echo "Created .env — fill in NEARAI_API_KEY, NEAR_ACCOUNT_ID, NEAR_PRIVATE_KEY")

test:               ## backend unit tests (no network, no credits)
	cd backend && .venv/bin/python -m pytest -q

demo:               ## serve API + web app on http://127.0.0.1:8000
	$(BIN)/python -m uvicorn oathbox.app:app --app-dir backend --host 127.0.0.1 --port 8000

e2e:                ## real run: seal sample room, ask, verify, tamper (1 TEE call, 2 testnet txs)
	cd backend && .venv/bin/python scripts/e2e.py

contract:           ## rebuild the wasm (needs Rust + cargo-near; the prebuilt one is in contract/res)
	cd contract && ./build.sh
