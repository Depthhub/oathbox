# Oathbox — Research Findings & Build Plan

Companion to `Proofroom-PRD 3` (PRD written under the old name) (+ the 7-step `/ask` fix). Researched 2026-11-11 from the live docs listed in §9.
Everything marked **VERIFY** was not confirmed and must be checked on first contact with the live API / package.

---

## 0. Progress log

**2026-11-12 — TEE path proven live (`backend/scripts/smoke.py`)**
- Model: `Qwen/Qwen3.6-35B-A3B-FP8` (`owned_by: "nearai"` in `/v1/models` = NEAR TEE fleet; `"attested 3p"` = third-party). Backup `deepseek-ai/DeepSeek-V4.1-Flash-1017` also returns a full model attestation. The PRD's model IDs were right after all.
- All 13 checks pass on real evidence: nonce echo, TDX quote (`UpToDate`), not debug, signer bound, nonce bound, MRCONFIGID = app_compose, RTMR3 replay, GPU nonce, NRAS verdict, `provider_tee` signature, signature covers exact bytes, signature valid, signer = attested key. ~5–11 s per ask, ~3.4k prompt tokens (mostly cached), ~100 completion tokens.
- Resolved VERIFY items: `dcap_qvl.get_collateral_and_verify(raw_quote, pccs_url=None)` is async, `to_json()` → `report.TD10.{report_data, mr_config_id, rt_mr3, td_attributes}`; `near-kit` 1.3.0 `Near(network, account_id=, private_key=)` with `.call/.view/.deploy_contract/.create_account` and `AsyncNear`. Real report shape: `model_attestations[].info` and `.info.tcb_info` are objects (code accepts strings too).
- Decision: **reasoning off** (`chat_template_kwargs.enable_thinking=false`). With it on, reasoning ate the whole 600-token budget, and the raw response the investor keeps would carry unfiltered reasoning over private files.
- Decision: **post-filter split** — 40+ chars blocked when the run looks like code/data (symbols or digit-comma runs), 64+ for plain prose. A flat 40 blocked a correct paraphrase sharing a 49-char everyday phrase with a TODO comment. Secret-window rule unchanged. README must state both thresholds.
- Prompt rule added: never quote any file text (comments, READMEs, TODOs); paraphrase.
- Next: contract (`contract/`), deploy to testnet, `chain.py`, then FastAPI.

**2026-11-12 — Contract deployed to testnet**
- `oathbox.builtbysammy.testnet`, deploy tx `3HEXFFVP1pBHdRt3hpJzow4qy8TGXL33hjHvwokNkk2j`. On-chain code sha256 = local `contract/res/oathbox_contract.wasm` = `043bd113…af2c3` (170 KB). Initialised (`receipt_count() == 0`). Funded 2.5 NEAR.
- 10 unit tests pass. Storage is caller-paid: attach a deposit, exact cost kept, remainder refunded (`.detach()`ed promise).
- Toolchain: Windows has no C linker, so contract builds run in WSL Ubuntu (build-essential, rustup, cargo-near 0.23 from crates.io — the curl|sh installer was blocked). `contract/build.sh` honours `CARGO_TARGET_DIR`.
- Testnet NEAR: near-faucet.io capped at 2 NEAR then errored; used `cargo near create-dev-account` (account-creation faucet, 10 NEAR) on throwaway `obnoxious-glue.testnet` and swept 9.95 NEAR to `builtbysammy.testnet`. Throwaway key stays in WSL `~/.near-credentials`.
- Deploy funding default lowered to 1.8 NEAR (`DEPLOY_FUNDING` env overrides).
- Hackathon payout field = mainnet `builtbysammy.near` (name only; its key must never be in `.env`).
- Next: `backend/oathbox/chain.py` (near-kit: commit_dataroom, record_receipt, views), then FastAPI routes.

**2026-11-12 — Backend wired to chain; full flow proven (`backend/scripts/e2e.py`)**
- Sample room `ledgerlight-demo` committed: root `623aca24…f254c`, tx `Dz41iPnf1XZVe2Fu7iuaXLuog63qp6XGW9bXJj9QJpJK`. **Immutable** — if sample files ever change, use a new room id.
- First real receipt #0, tx `4RXpq783rnK5hgvcFxg3X5YAeiVSWLHWXouTMGKVqKZg` (use in README).
- Outsider verify (receipt id only) re-runs every TEE check from the public attestation report and recovers the signer from on-chain hashes alone (signed text = `model:request_hash:response_hash`). Investor verify (bundle) adds response/answer/question hashes; founder-side rebuilds the request from the private room. Forged answer → `failed`. Tamper → 409 `room_changed` naming `metrics.csv`, no TEE call, nothing recorded.
- New check status `na` (not applicable to this viewer) — ignored by the badge.
- Retention: server keeps only public attestation reports, commit manifests (path + hash), and uploaded rooms. Q/A/raw responses live only in the investor's bundle.
- API: `backend/oathbox/app.py` (10 routes under `/api`), serves `web/dist` when built. 37 tests pass (API tests use a fake chain and a copy of the room).
- Next: web UI (founder / investor / verify pages), Makefile, README.

**2026-11-12 — Web UI (Kujua design system) + room upload**
- `web/` Vite + React, styled with the Kujua "Soft Editorial Productivity" tokens (design.json) adapted to a web bento grid; light + dark. Backend serves `web/dist` (index.html no-cache).
- Routes: `#ask[-room]`, `#founder[-room]`, `#new`, `#verify-<n>`. Founders upload a room (≤300 KB, ≤100 files; whole room goes into model context), seal it on NEAR, and share `#ask-<room>`. Failed commits free the name. Binary files are sealed but flagged "Model can't read".
- Verified in the UI against testnet + TEE: tamper refusal, receipt #2 verified 18/18 with the investor's saved copy, uploaded `harbor-test-room` answered correctly (receipt #4). No horizontal scroll at 375px.
- `.env.example` had a real NEAR AI key in it; blanked before the first commit (never committed). Keys live only in `.env`.
- 40 backend tests pass.
- Next: README with quickstart + receipt links, demo video.

**2026-11-12 — Founders connect their own NEAR wallet**
- Wallet Selector 10.1.4 (MyNearWallet, Meteor) + `buffer` polyfill. Sign-in = NEP-413 signed message (no tx, no fee); backend verifies with near-kit `verify_message` AND that the key is a FullAccess key of the account on chain; issues an HMAC session token (12 h). Challenges are single-use, 5 min.
- Founder rooms are sealed by the founder's wallet, not the server: upload stages files (pending, name held 1 h for that founder) → ONE wallet tx with `commit_dataroom` + `set_backend(server)` → `/confirm` checks owner + root on chain. The server only seals the bundled sample room.
- Owner-only: file names, room list, finish/approve buttons. Investors see the commitment only. `/ask` refuses (409 `server_not_approved`) until the owner allow-lists this server.
- Wallet popups must open from a click, so Connect / Confirm / Seal are separate buttons.
- Bundle grew to ~456 KB gzip (wallet libs). 43 backend tests pass.
- Real wallet sign-in + seal confirmed by the user (kettlebird-dataroom, 27 files, owner builtbysammy.testnet).

**2026-11-12 — Sample room off the site; Built on NEAR**
- UI no longer shows Ledgerlight (no suggestions, tamper card, "fictional" note); `/api/rooms` lists only the signed-in founder's rooms. `#ask` and `#founder` without a room are home pages (paste a room link / your rooms). The sample still works at `#ask-ledgerlight-demo` for `scripts/e2e.py`.
- NEAR logo SVGs copied unaltered from near.org's header (near.org/brand is 404) into `web/src/near-logo.jsx`; mark in the network pill, "Built on NEAR" badge in the footer.

**2026-11-12 — New Oathbox logo (mascot)**
- User's orange-cube mascot: original in `web/public/brand/oathbox-mascot-original.webp`; face cropped with transparent background to `oathbox-mark-{64,128,512}.png` (header mark, favicon, touch icon). Backend now serves files from `web/dist` (resolved path must stay inside dist; traversal falls back to index.html).

**2026-11-12 — Disclosure filter judged by file type**
- "Tell me about this project" on a pitch room was withheld: `$`/`%`/`:` made pitch prose count as code (40-char limit). Now: data files (.csv/.json/.env/…) every 40-char run; code files 40-char code-looking runs (unchanged); documents (.md/.txt) only fenced ``` blocks at 40; all files 120 chars for any text (was 64). Secrets rule unchanged. README must state these limits. 46 tests pass.

---

## 1. What the research changed (PRD v4 deltas)

These are not polish. Each one changes code or a claim.

| # | Finding | Change to PRD |
|---|---|---|
| 1 | Docs require **preflight**: verify the attestation (fresh nonce) *before* the completion, then match the completion's signer to a signer you verified *before* the call. A later report can't stand in. | Reorder `/ask`: attestation + verify **before** chat. New order in §4.3. |
| 2 | Python DCAP verification is ~45 lines with `dcap-qvl`, and NEAR's docs publish a reference helper (`check_near_report`): quote, debug bit, report_data = signer‖nonce, MRCONFIGID = compose hash, RTMR3 replay. | Move **DCAP verification to Must-have**. It's feasible on Day 1–2. "Verified" becomes achievable, not aspirational. |
| 3 | Privacy track prompt asks for: fresh nonce, a **"Verified" panel listing what was checked**, and **"keep nothing server-side after a response returns"** (stated in README and obvious in code), plus fictional sample docs. | Drop server-side storage of raw request/response. Use a client-held **receipt bundle** (§4.5). Founder audit log shows on-chain receipts only. |
| 4 | Signed text is `"{model_id}:{request_hash}:{response_hash}"` for `signature_kind=provider_tee`, `"{req}:{resp}"` for `gateway`. Gateway signs if you **stream**, if a **model alias** is resolved, or on the Responses API. | Non-streaming chat, canonical model ID, `x-no-aliasing: true`, require `signature_kind == "provider_tee"`. Send `Accept-Encoding: identity`. |
| 5 | Signatures are ECDSA EIP-191 (`eth_account.encode_defunct` + `Account.recover_message`). 404 right after completion is normal; retry ~5×1s. Retention window **not documented**. | Fetch signature immediately with bounded retry; failure → receipt not recorded, answer shown as "unverified". |
| 6 | Model IDs in the PRD (`Qwen/Qwen3.6-35B-A3B-FP8`, `deepseek-ai/DeepSeek-V4.1-Flash-1017`) appear **nowhere** in the docs read. Docs show `zai-org/GLM-5.1-FP8`, `z-ai/glm-5.3-flash`; the verifier defaults to `deepseek-ai/DeepSeek-V3.1`. `/v1/models` has **no documented TEE field**. | Pick model from the catalog's **"Confidential TEE"** tier (not "3P" or "Incognito"), confirm `model_attestations[]` is non-empty for it, then hardcode the allow-list. **VERIFY Day 1.** |
| 7 | Same-model instances share one signing key → a signer match proves "a genuine TEE running this model", not "this exact instance". NRAS GPU JWT signature is not verified by either reference repo. | Add both to README limitations. GPU check labelled "NRAS verdict (JWT signature not checked)" unless you add JWKS validation (stretch). |
| 8 | Python NEAR signing: docs now point to **`near-kit`** (`pip install near-kit`, import `near`, Python 3.11+, `Near(network="testnet", account_id=…, private_key=…)`, `client.call(contract, method, args, gas="30 Tgas")`). `py-near` is the older alternative. | Use `near-kit`; fallback `py-near`; last resort shell out to `near` CLI. **VERIFY API on install.** |
| 9 | Storage = 1e19 yocto/byte (1 NEAR / 100 KB). A receipt is ~700–900 bytes → **~0.008 NEAR each**. Faucet gives free testnet NEAR. | Keep the ~0.01 NEAR estimate; fund contract with ≥5 NEAR. |
| 10 | Hackathon rules: repo **public by 14 Nov 23:59 UTC**; README must **list libraries and AI-generated code**; LICENSE (MIT fine); payout needs a **mainnet** NEAR account; form "idea" field 20–2000 chars; demo link = X post; local-only demo is OK **with a video**; hosted demo is a plus (keep up to Nov 18–25). Only code written after Oct 19 counts. | Add a "Built with / AI assistance" README section, LICENSE, and a mainnet payout account to the Sat checklist. |
| 11 | 40-char verbatim filter **won't catch a short API key** (most fake keys are <40 chars). | Post-filter gets a second rule: block any answer containing a string flagged by a secret regex scan of the data room (§4.4). |
| 12 | Story "Who owns >10%?" collides with "never output personal names". | Sample cap table uses role labels ("Founder A", "Seed Fund I (fictional)"), so a natural answer needs no names. |

### Revised `/ask` order (replaces the 7 steps)
1. Re-hash room, compare to on-chain root. Mismatch → refuse, record nothing, return both roots.
2. Fresh 32-byte nonce → `GET /v1/attestation/report?model=…&provider=near&signing_algo=ecdsa&nonce=…` (`x-no-aliasing: true`) → run `check_near_report` on every `model_attestations[]` candidate + NRAS GPU check. Keep the verified signer set. Store the report publicly by its sha256. (Cache per process for ≤5 min if latency hurts; README must then say nonces are per-cache-window, not per-ask.)
3. Build request JSON deterministically, POST raw bytes (non-stream, `x-no-aliasing`, `Accept-Encoding: identity`), keep exact response bytes → `request_hash`, `response_hash`.
4. `GET /v1/signature/{id}?model=…&signing_algo=ecdsa` with retry. Require `provider_tee`, text == `"{model}:{req}:{resp}"`, recovered signer ∈ verified signer set from step 2.
5. Post-filter. Reject → "Answer withheld by disclosure filter", record nothing.
6. `record_receipt` (with `attestation_checked_offchain = all step-2 checks passed`).
7. Return answer + receipt + tx link + **receipt bundle**. Discard request/response from memory.

---

## 2. Final technical decisions

| Area | Decision | Why |
|---|---|---|
| Frontend | **Vite + React + TypeScript**, plain CSS | Faster than Next for 3 pages; static build, served by FastAPI. |
| Backend | **Python 3.11+, FastAPI, httpx, dcap-qvl, eth-account, near-kit** | near-kit needs 3.11; dcap-qvl has Python bindings; reference helpers are Python. |
| Contract | **Rust, near-sdk 5.x, `IterableMap`/`LookupMap` from `near_sdk::store`** | Docs examples pin 5.29.0 — check crates.io for latest. |
| Contract build | `cargo near build non-reproducible-wasm` → `target/near/oathbox.wasm`, committed to `contract/res/` | Repro needs Docker; prebuilt wasm keeps quickstart toolchain-free. |
| Model | First "Confidential TEE" model from catalog that returns `model_attestations[]`; one backup | §1 #6. |
| Verification code | Port `check_near_report` + `verify_response_signature` from docs.near.ai reference (MIT nearai repos) into `backend/oathbox/verify.py` | Fail-closed, matches docs exactly. Credit in README. |
| TCB policy | Accept `{"UpToDate"}`; show `OutOfDate` as amber "TCB out of date" not green | Docs leave the set to you; nearai verifier accepts OutOfDate. Be explicit. |
| Retention | No server-side Q/A storage. Investor downloads/keeps receipt bundle. | Privacy track requirement. |
| Hosting | Local-only + video is sufficient. Stretch: host on a small VM Sat if time. | Rules allow it. |

---

## 3. Repo layout

```
oathbox/
├─ README.md               # AI screeners read first
├─ LICENSE                 # MIT
├─ Makefile                # install / contract / demo / test / verify-receipt
├─ .env.example            # NEARAI_API_KEY, NEAR_ACCOUNT_ID, NEAR_PRIVATE_KEY, CONTRACT_ID, MODEL_ID
├─ .gitattributes          # sample-dataroom/** -text
├─ contract/
│  ├─ Cargo.toml
│  ├─ src/lib.rs           # DataRoom, Receipt, 6 methods + unit tests
│  └─ res/oathbox.wasm   # prebuilt, committed
├─ backend/
│  ├─ pyproject.toml
│  ├─ oathbox/
│  │  ├─ hashing.py        # file_hash, leaf, root (byte-exact)
│  │  ├─ prompt.py         # system prompt + deterministic request builder
│  │  ├─ tee.py            # attestation fetch, chat (raw bytes), signature fetch
│  │  ├─ verify.py         # check_near_report, replay_rtmr3, NRAS, verify_response_signature
│  │  ├─ filter.py         # 40-char overlap + secret-token block
│  │  ├─ chain.py          # near-kit wrapper: commit, record, get_*
│  │  ├─ tamper.py         # reversible toggle, backup outside sample-dataroom/
│  │  └─ app.py            # FastAPI routes, serves web/dist
│  ├─ scripts/smoke.py     # one completion + full verification, prints every check
│  └─ tests/               # hashing determinism, filter, signature text, bundle verify
├─ web/                    # Vite React: /founder, /room/:id, /receipt/:id
├─ sample-dataroom/        # FICTIONAL — labelled in every file header
│  ├─ README.txt
│  ├─ repo/ (~10 files, 1 fake key, 1 test)
│  ├─ metrics.csv
│  └─ cap_table.csv
└─ scripts/deploy_contract.sh
```

---

## 4. Module specs

### 4.1 Hashing (`hashing.py`)
- Walk `sample-dataroom/`, skip nothing except `.tamper-backup` paths (backup lives outside the folder anyway).
- `rel = path.relative_to(root).as_posix()`; sort by `rel` as UTF-8 bytes.
- `file_hash = sha256(bytes)`; `leaf = sha256(rel.encode() + b"\x00" + file_hash_raw32)`; `root = sha256(b"".join(leaves))` → hex.
- Test: hash is identical on Windows and WSL checkout; flipping one byte changes root; restore returns exact root.

### 4.2 Prompt / request builder (`prompt.py`)
- Body = `json.dumps({"model", "messages":[system, user], "temperature":0, "max_tokens":400, "stream":false}, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode("utf-8")`.
- User message = file manifest + each file as `=== path ===\n<content>` + `QUESTION: …`.
- Deterministic → founder can rebuild the exact request bytes from (data room, question) and recompute `request_hash` without storing anything.

### 4.3 TEE client (`tee.py`) — exact endpoints
- Base `https://cloud-api.near.ai`, `Authorization: Bearer $NEARAI_API_KEY`.
- `GET /v1/attestation/report` params `signing_algo=ecdsa, nonce=<64 hex>, model=<id>, provider=near`; headers `Accept: application/json`, `x-no-aliasing: true`. Response: `gateway_attestation`, `model_attestations[]` each with `intel_quote, event_log (JSON string), request_nonce, signing_address, signing_algo, signing_public_key, nvidia_payload (JSON string), info.tcb_info.app_compose`. **No `report_data` in model reports — read it from the verified quote.**
- `POST /v1/chat/completions` raw bytes; headers add `Content-Type: application/json`, `x-no-aliasing: true`, `Accept-Encoding: identity`. Keep `resp.content` (bytes) for hashing; chat `id` → signature lookup.
- `GET /v1/signature/{id}?model=<id>&signing_algo=ecdsa` → `text, signature, signing_address, signing_algo, signature_kind`. 404 → retry 5×1s. 2xx with `error_code` = unavailable.

### 4.4 Verification (`verify.py`) — the checks the panel lists
| Check | Source | Pass rule |
|---|---|---|
| Room root == on-chain root | contract view | equal |
| TDX quote valid | `dcap_qvl.get_collateral_and_verify` | status ∈ accepted set |
| Not debug TD | `td_attributes[0] & 1` | 0 |
| Signer bound to quote | `report_data[0:32]` | `signing_address` right-padded to 32 |
| Our nonce in quote | `report_data[32:64]` + `request_nonce` | equal to nonce bytes / hex |
| Compose measured | `mr_config_id` | `0x01 ‖ sha256(app_compose) ‖ 15×0x00` |
| Event log matches | RTMR3 replay | equals `rt_mr3` |
| GPU attested | NRAS `POST https://nras.attestation.nvidia.com/v3/attest/gpu` | payload nonce match + `x-nvidia-overall-att-result == true` (JWT sig unchecked — label it) |
| Completion signed in TEE | EIP-191 recover | recovered == `signing_address`, kind `provider_tee`, text `model:req:resp` |
| Signer == attested signer | compare | signer ∈ verified `model_attestations[]` signers |
| request_hash | rebuild from room+question | founder-side only |
| response_hash | sha256(bundle.raw_response) | investor-side (has bundle) |
| answer_hash / question_hash | sha256 of text | anyone with bundle |

Badge: **Verified** = every applicable check passed. **Attestation fetched (quote unchecked)** = only if DCAP step errors on infra (e.g. PCCS unreachable), never on a failed check. **Failed** = any check failed. dcap-qvl needs outbound HTTPS to Phala PCCS (default) — **VERIFY** the Python signature for passing Intel PCS instead.

Post-filter (`filter.py`): (a) reject if answer shares any ≥40-char substring with any file (rolling-hash set of all 40-grams); (b) reject if answer contains any token found by secret regexes over the room (`sk_…`, `AKIA…`, `ghp_…`, generic ≥20-char base62/hex after `key|secret|token =`). Both tested.

### 4.5 Receipt bundle (client-held)
```json
{ "receipt_id": 7, "contract": "oathbox.<you>.testnet", "dataroom_id": "acme-demo",
  "question": "...", "answer": "...", "model_id": "...",
  "raw_response_b64": "...", "signature": { ...as returned... },
  "attestation_hash": "...", "nonce": "..." }
```
Investor UI keeps it in memory + "Download receipt" button. `/verify` accepts `{receipt_id}` (public checks only) or `{receipt_id, bundle}` (adds response/answer/question hash checks). Attestation reports served at `GET /attestations/{sha256}` (public, contains no room data).

### 4.6 Contract (`lib.rs`)
- State: `owner_of_rooms: IterableMap<String, DataRoom>`, `backends: LookupMap<String, Vec<AccountId>>` (or `LookupSet<(String, AccountId)>`), `receipts: Vector<Receipt>`, `by_room: LookupMap<String, Vec<u64>>`.
- `commit_dataroom`: panic if id exists; owner = predecessor; validate 64-hex root.
- `record_receipt`: panic unless predecessor is owner or allow-listed; panic if `dataroom_root != room.root_hash`; validate hex lengths; push; emit `EVENT_JSON` log for explorer readability.
- `set_backend`, `get_dataroom`, `get_receipt`, `get_receipts(dataroom_id, from, limit≤50)`.
- Unit tests (≥4): commit immutable; non-owner record panics; wrong root panics; allow-listed backend can record.
- Deploy:
  ```
  near create-account oathbox-<you>.testnet --useFaucet --networkId testnet
  cargo near build non-reproducible-wasm
  near contract deploy oathbox-<you>.testnet use-file ./target/near/oathbox.wasm without-init-call network-config testnet sign-with-keychain send
  ```
  (WSL keychain issue → use `save-to-legacy-keychain` in the create-account long form.)

### 4.7 Web (3 pages)
- **/founder** — pick folder/zip (or "Use sample data room") → root hash, file count, commit tx link; read-only disclosure rules; on-chain receipt list (hashes, time, tx). Tamper toggle lives here (labelled DEMO).
- **/room/:id** — 3 suggested questions as chips; answer card + status badge + "View receipt" + "Download receipt".
- **/receipt/:id** — check list (§4.4 table) each pass / fail / founder-side / n.a., with the reason; explorer links; drop-zone to load a bundle for the extra hash checks.
- Never render file contents anywhere. Founder page shows names + sizes only.

---

## 5. Day-by-day plan (WAT, UTC+1)

### Wed Nov 11 (tonight, ~3h)
- [ ] Claim $10 credits at nearbuilders.org/join → dashboard → API key into `.env`.
- [ ] Install toolchain in **WSL**: rustup + `wasm32-unknown-unknown`, cargo-near, near-cli-rs; Python 3.11+.
- [ ] Create testnet accounts (contract + backend/owner) via faucet.
- [ ] Repo skeleton, `.gitattributes`, LICENSE, `.env.example`, sample data room, `hashing.py` + tests.
- [ ] `GET /v1/models` + catalog → choose TEE model; record ID + price per token.

### Thu Nov 12 — "prove the TEE path end to end in a script"
- [ ] 09–12 `tee.py` + `verify.py` + `scripts/smoke.py`: attestation → all checks → chat → signature → signer match. **Gate: smoke prints every check green.**
- [ ] 12–14 `prompt.py` deterministic builder; `filter.py` + tests; measure tokens/cost per ask.
- [ ] 14–18 Contract `lib.rs` + unit tests; build; deploy to testnet; commit wasm.
- [ ] 18–21 `chain.py` with near-kit: commit + record + views from Python. **Gate: one real receipt on explorer.**

### Fri Nov 13 — "product"
- [ ] 09–12 FastAPI routes (`/rooms`, `/rooms/{id}/ask`, `/receipts/{id}`, `/attestations/{h}`, `/verify`, `/demo/tamper`) + tamper module.
- [ ] 12–19 Web: three pages, badge states, bundle download/upload.
- [ ] 19–22 `make install`, `make demo` (starts backend serving built web, prints URL); first full fresh-clone run in a clean folder.

### Sat Nov 14 — "ship"
- [ ] 09–12 Fresh clone on a second environment (WSL clean dir) following README only; fix every snag.
- [ ] 12–14 README final (§6), receipts from a real run linked.
- [ ] 14–16 Record 60s video (script §8 of PRD); upload.
- [ ] 16–17 Make repo public; tag `hackathon-submission`.
- [ ] 17–18 **You** post on X: "built at NEAR HACKATHON", @NEARProtocol, #NEARHackathon, video.
- [ ] 18–20 **You** submit form: name, lead, email, team size 1, track `privacy`, **mainnet** payout account, repo URL, X post URL, idea text (≤2000 chars, prepared in `SUBMISSION.md`). Never resubmit; edits via /request-changes.

**Cut order** (unchanged + new): founder receipt list → bundle drop-zone on verify page → RTMR3 replay (keep the rest of DCAP) → hosted demo. Never cut: DCAP quote+report_data checks, signature check, README, video, X post.

---

## 6. README outline (screeners run it)
1. One-liner + 3 sentences.
2. 60s video + X post links.
3. Quickstart: prereqs (Python 3.11+, Node 22+; Rust **not** required), `cp .env.example .env`, `make install`, `make demo` → "you will see: root hash `…` committed at tx `…`; ask 'Is MRR growing?' → green Verified badge listing 12 checks".
4. Deployed contract ID + explorer link to a real receipt.
5. "What is verified" table (§4.4) and "What is not": GPU JWT signature, instance identity (shared key), answer correctness, completeness of founder's upload.
6. Privacy: no server-side retention after response (point to the exact code lines), data room only sent to the TEE endpoint.
7. Architecture diagram.
8. Built with: libraries + licenses; ported MIT code from nearai-cloud-verifier / docs.near.ai reference; AI assistance disclosure.
9. Limitations & next steps.

---

## 7. Open questions to resolve on Day 1 (VERIFY)
1. Exact TEE model ID and whether `model_attestations[]` is returned for it.
2. dcap-qvl Python version, `get_collateral_and_verify` signature, and `to_json()` shape (`report.TD10.*`).
3. near-kit API names (constructor, `call`, `view`, how tx hash is returned for explorer link).
4. Signature retention window (ask in NEAR Builders Discord if 404s persist).
5. Credit burn per ask with the chosen model (budget ≤ $3 for dev, ≤ $1 for demo recording).
6. Whether the Privacy track judges expect the near-ai-cloud "agent skill" workflow (mentioned in the track prompt) — optional to mention in README.

---

## 8. Things only you can do (I won't do these)
- Claim credits / create API key; create the mainnet payout account.
- Make the repo public, post on X, submit the form.
- Approve any testnet transaction signing from your key (I'll script it; you run it or approve each run).

---

## 9. Sources read
- NEAR AI Cloud verification: https://docs.near.ai/cloud/verification/cloud-api (+ gateway-attestation.md, model-attestations.md, response-signatures.md, tls.md), https://docs.near.ai/cloud/models.md, reference helpers https://docs.near.ai/cloud/verification/reference/quote-nonce-signer.md, response-signature-verification.md, verification-policy.md
- https://github.com/near-examples/nearai-cloud-verification-example (JS demo; explicitly not a full verifier)
- https://github.com/nearai/nearai-cloud-verifier (Python+TS, MIT; `py/model_verifier.py`, `py/chat_verifier.py`)
- Hackathon: https://nearhackathon.com/HACKATHON.md, https://nearhackathon.com, Privacy track prompt https://github.com/nearai/near-hackathon-prompt-examples/blob/main/tracks/03-privacy.md
- NEAR dev docs: https://docs.near.org/smart-contracts/quickstart, /smart-contracts/release/deploy, /tools/cli, /tools/sdk, /tools/near-api, /smart-contracts/anatomy/collections, /smart-contracts/testing/unit-test, /protocol/storage/storage-staking
- py-near (fallback): https://py-near.readthedocs.io/en/latest/clients/delegate.html
