import hashlib
import shutil

import pytest

from oathbox.hashing import digest_files, digest_room, leaf_hash, list_files


def test_known_vector():
    # Hand-computed from the documented rules, so the README can quote it.
    files = [("b.txt", b"world"), ("a.txt", b"hello")]
    fa = hashlib.sha256(b"hello").digest()
    fb = hashlib.sha256(b"world").digest()
    la = hashlib.sha256(b"a.txt\x00" + fa).digest()
    lb = hashlib.sha256(b"b.txt\x00" + fb).digest()
    expected = hashlib.sha256(la + lb).hexdigest()
    assert digest_files(files).root == expected


def test_order_independent():
    a = [("x/1.py", b"1"), ("x/2.py", b"2"), ("y.csv", b"3")]
    assert digest_files(a).root == digest_files(list(reversed(a))).root


def test_any_byte_change_changes_root():
    base = digest_files([("f.csv", b"month,mrr\n2026-01,100\n")]).root
    assert digest_files([("f.csv", b"month,mrr\n2026-01,101\n")]).root != base
    # CRLF vs LF must count as a change (no newline normalisation)
    assert digest_files([("f.csv", b"month,mrr\r\n2026-01,100\r\n")]).root != base


def test_rename_changes_root():
    assert digest_files([("a.txt", b"x")]).root != digest_files([("b.txt", b"x")]).root


def test_duplicate_paths_rejected():
    with pytest.raises(ValueError):
        digest_files([("a", b"1"), ("a", b"2")])


def test_leaf_rejects_bad_input():
    with pytest.raises(ValueError):
        leaf_hash("a", b"short")
    with pytest.raises(ValueError):
        leaf_hash("a\x00b", bytes(32))


def test_sample_room_uses_posix_paths(sample_room):
    paths = [rel for rel, _ in list_files(sample_room)]
    assert "repo/ledgerlight/config.py" in paths
    assert all("\\" not in p for p in paths)
    assert paths == sorted(paths, key=lambda p: p.encode())


def test_sample_room_has_no_crlf(sample_room):
    # Guard for .gitattributes: a Windows checkout must not add CR bytes.
    for rel, p in list_files(sample_room):
        assert b"\r\n" not in p.read_bytes(), f"{rel} has CRLF line endings"


def test_copy_and_restore_root(sample_room, tmp_path):
    room = tmp_path / "room"
    shutil.copytree(sample_room, room)
    original = digest_room(room).root
    assert original == digest_room(sample_room).root

    target = room / "metrics.csv"
    saved = target.read_bytes()
    target.write_bytes(saved.replace(b"47950", b"57950"))
    assert digest_room(room).root != original

    target.write_bytes(saved)
    assert digest_room(room).root == original
