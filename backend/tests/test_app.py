"""API tests with a fake chain and no TEE calls (nothing leaves the machine)."""

import base64
import shutil

import near
import pytest
from fastapi.testclient import TestClient

import oathbox.app as appmod
from oathbox.hashing import digest_room


class FakeChain:
    contract_id = "oathbox.test.testnet"
    account_id = "test.testnet"

    def __init__(self, root):
        self.rooms = {"ledgerlight-demo": {"id": "ledgerlight-demo", "owner": "test.testnet",
                                           "root_hash": root, "file_count": 13, "created_at": "0"}}
        self.recorded = []
        self.backends = {}
        self.full_keys = {}  # account -> set of public keys

    def get_backends(self, rid):
        return self.backends.get(rid, [])

    def is_full_access_key(self, account, pk):
        return pk in self.full_keys.get(account, set())

    def wallet_seal(self, rid, owner, root, count, approve=True):
        """What the founder's wallet transaction does on chain."""
        self.rooms[rid] = {"id": rid, "owner": owner, "root_hash": root, "file_count": count, "created_at": "0"}
        if approve:
            self.backends[rid] = [self.account_id]

    def tx_url(self, h):
        return f"https://example.invalid/tx/{h}"

    def account_url(self, a=None):
        return "https://example.invalid/acct"

    def get_dataroom(self, rid):
        return self.rooms.get(rid)

    def commit_dataroom(self, rid, root, count):
        if getattr(self, "fail_commit", False):
            raise appmod.ChainError("simulated RPC failure")
        self.rooms[rid] = {"id": rid, "owner": self.account_id, "root_hash": root,
                           "file_count": count, "created_at": "0"}
        return self.rooms[rid], "COMMITTX"

    def record_receipt(self, **kw):
        self.recorded.append(kw)
        return 0, "TX"


@pytest.fixture
def client(sample_room, tmp_path, monkeypatch):
    room = tmp_path / "room"  # never touch the real sample room
    shutil.copytree(sample_room, room)
    monkeypatch.setattr(appmod, "SAMPLE_DIR", room)
    monkeypatch.setattr(appmod, "SAMPLE_ROOM_ID", "ledgerlight-demo")  # independent of .env
    monkeypatch.setattr(appmod, "tamper", appmod.Tamper(room, tmp_path / "state"))
    monkeypatch.setattr(appmod, "store", appmod.Store(tmp_path / "state"))
    monkeypatch.setattr(appmod, "auth", appmod.Auth(tmp_path / "state", "test-secret"))
    with TestClient(appmod.app) as c:
        fake = FakeChain(digest_room(room).root)
        appmod.app.state.chain = fake
        yield c, fake


def test_config_and_room(client):
    c, _ = client
    cfg = c.get("/api/config").json()
    assert cfg["sample_room_id"] == "ledgerlight-demo"
    room = c.get("/api/rooms/ledgerlight-demo").json()
    assert room["matches_chain"] is True
    assert all("content" not in f for f in room["local"]["files"])


def test_tampered_room_is_refused_and_nothing_recorded(client, monkeypatch):
    c, fake = client

    async def must_not_run(*a, **k):
        raise AssertionError("TEE must not be called for a changed room")

    monkeypatch.setattr(appmod, "run_ask", must_not_run)
    assert c.post("/api/demo/tamper", json={"on": True}).json()["matches_chain"] is False
    r = c.post("/api/rooms/ledgerlight-demo/ask", json={"question": "Is MRR growing?"})
    assert r.status_code == 409
    body = r.json()
    assert body["status"] == "room_changed"
    assert body["changed_files"] == []  # no commit-time manifest in this test
    assert body["onchain_root"] != body["local_root"]
    assert fake.recorded == []
    assert c.post("/api/demo/tamper", json={"on": False}).json()["matches_chain"] is True


def test_bad_room_id_rejected(client):
    c, _ = client
    assert c.get("/api/rooms/..%2Fsecret").status_code in (400, 404)
    assert c.get("/api/rooms/BAD!").status_code == 400


def _files(*pairs):
    return [("files", (name, data, "application/octet-stream")) for name, data in pairs]


def _as(account):
    return {"Authorization": f"Bearer {appmod.auth.issue(account)}"}


def test_wallet_sign_in_checks_signature_and_key_ownership(client):
    c, fake = client
    kp = near.generate_key()
    signer = near.KeyPairSigner("founder.testnet", kp)
    pk = str(kp.public_key)

    def attempt(account="founder.testnet", tamper_sig=False):
        ch = c.get("/api/auth/challenge").json()
        signed = near.nep413.sign_message(signer, ch["message"], ch["recipient"], base64.b64decode(ch["nonce"]))
        sig = signed.signature
        if tamper_sig:
            raw = bytearray(base64.b64decode(sig)); raw[0] ^= 1; sig = base64.b64encode(bytes(raw)).decode()
        return ch, c.post("/api/auth/verify", json={"account_id": account, "public_key": pk,
                                                   "signature": sig, "nonce": ch["nonce"]})

    _, r = attempt()
    assert r.status_code == 401, "key is not a FullAccess key of the account yet"
    fake.full_keys["founder.testnet"] = {pk}
    ch, r = attempt()
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json() == {"account_id": "founder.testnet"}
    # the same challenge can't be replayed
    replay = c.post("/api/auth/verify", json={"account_id": "founder.testnet", "public_key": pk,
                                              "signature": "x" * 20, "nonce": ch["nonce"]})
    assert replay.status_code == 401
    assert attempt(tamper_sig=True)[1].status_code == 401
    assert attempt(account="someone-else.testnet")[1].status_code == 401
    assert c.get("/api/auth/me", headers={"Authorization": "Bearer forged.token"}).json() == {"account_id": None}


def test_founder_uploads_seals_from_wallet_and_confirms(client):
    c, fake = client
    assert c.post("/api/rooms", data={"room_id": "acme-seed"}, files=_files(("a.txt", b"x"))).status_code == 401

    r = c.post("/api/rooms", data={"room_id": "acme-seed"}, headers=_as("acme.testnet"),
               files=_files(("README.md", b"# Acme\n"), ("finance/metrics.csv", b"month,mrr\n2026-10,100\n")))
    assert r.status_code == 200, r.text
    staged = r.json()
    tx = staged["transaction"]
    assert tx["receiver_id"] == fake.contract_id
    assert [x["method"] for x in tx["calls"]] == ["commit_dataroom", "set_backend"]
    assert tx["calls"][1]["args"] == {"dataroom_id": "acme-seed", "account": fake.account_id}
    assert staged["room"]["status"] == "pending"
    assert fake.rooms.get("acme-seed") is None, "the server must not seal founder rooms itself"

    # confirm before the wallet transaction lands
    assert c.post("/api/rooms/acme-seed/confirm", headers=_as("acme.testnet")).status_code == 409
    fake.wallet_seal("acme-seed", "acme.testnet", staged["root_hash"], staged["file_count"])
    # someone else can't confirm it
    assert c.post("/api/rooms/acme-seed/confirm", headers=_as("mallory.testnet")).status_code == 403
    room = c.post("/api/rooms/acme-seed/confirm", headers=_as("acme.testnet")).json()
    assert room["matches_chain"] and room["is_owner"] and room["backend_approved"]
    assert [f["path"] for f in room["local"]["files"]] == ["README.md", "finance/metrics.csv"]

    # only the owner sees it in their list, and only the owner sees file names
    assert [x["id"] for x in c.get("/api/rooms", headers=_as("acme.testnet")).json()] == ["acme-seed"]
    assert [x["id"] for x in c.get("/api/rooms", headers=_as("mallory.testnet")).json()] == []
    assert [x["id"] for x in c.get("/api/rooms").json()] == []
    public = c.get("/api/rooms/acme-seed").json()
    assert public["matches_chain"] is True and "files" not in public["local"]
    # the name is now taken for everyone
    assert c.post("/api/rooms", data={"room_id": "acme-seed"}, headers=_as("acme.testnet"),
                  files=_files(("a.txt", b"x"))).status_code == 409


def test_pending_name_is_held_for_its_founder(client):
    c, _ = client
    ok = c.post("/api/rooms", data={"room_id": "held"}, headers=_as("a.testnet"), files=_files(("a.txt", b"1")))
    assert ok.status_code == 200
    assert c.post("/api/rooms", data={"room_id": "held"}, headers=_as("b.testnet"),
                  files=_files(("a.txt", b"2"))).status_code == 409
    # the same founder can re-upload before sealing
    again = c.post("/api/rooms", data={"room_id": "held"}, headers=_as("a.testnet"), files=_files(("b.txt", b"3")))
    assert again.status_code == 200
    assert [f["path"] for f in again.json()["room"]["local"]["files"]] == ["b.txt"]


def test_ask_refused_until_founder_approves_server(client, monkeypatch):
    c, fake = client

    async def must_not_run(*a, **k):
        raise AssertionError("TEE must not be called before the server is approved")

    monkeypatch.setattr(appmod, "run_ask", must_not_run)
    staged = c.post("/api/rooms", data={"room_id": "noapprove"}, headers=_as("acme.testnet"),
                    files=_files(("a.txt", b"x"))).json()
    fake.wallet_seal("noapprove", "acme.testnet", staged["root_hash"], 1, approve=False)
    r = c.post("/api/rooms/noapprove/ask", json={"question": "anything in here?"})
    assert r.status_code == 409 and r.json()["status"] == "server_not_approved"
    assert fake.recorded == []


def test_upload_rejects_bad_input(client):
    c, _ = client
    h = _as("acme.testnet")
    assert c.post("/api/rooms", data={"room_id": "x1"}, headers=h, files=_files(("../evil.txt", b"x"))).status_code == 400
    assert c.post("/api/rooms", data={"room_id": "x2"}, headers=h, files=_files(("a.txt", b"1"), ("a.txt", b"2"))).status_code == 400
    big = b"x" * (appmod.MAX_UPLOAD_BYTES + 1)
    assert c.post("/api/rooms", data={"room_id": "x3"}, headers=h, files=_files(("big.txt", big))).status_code == 413
    assert c.post("/api/rooms", data={"room_id": "ledgerlight-demo"}, headers=h, files=_files(("a.txt", b"x"))).status_code == 400
    assert c.post("/api/rooms", data={"room_id": "Bad Name"}, headers=h, files=_files(("a.txt", b"x"))).status_code == 400
    assert [x["id"] for x in c.get("/api/rooms", headers=h).json()] == []


def test_server_only_seals_the_sample_room(client):
    c, _ = client
    c.post("/api/rooms", data={"room_id": "mine"}, headers=_as("acme.testnet"), files=_files(("a.txt", b"x")))
    assert c.post("/api/rooms/mine/commit").status_code == 403
