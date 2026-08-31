"""The session cache holds a refresh token, so its permissions and failure modes matter."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from pymysa import session_store
from pymysa.auth import Tokens


def _tokens() -> Tokens:
    return Tokens(
        id_token="id", access_token="access", refresh_token="refresh", expires_at=1.0
    )


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    session_store.save("me@example.com", _tokens(), path)
    loaded = session_store.load(path)
    assert loaded is not None
    username, tokens = loaded
    assert username == "me@example.com"
    assert tokens.refresh_token == "refresh"


def test_file_is_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    session_store.save("me@example.com", _tokens(), path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600, f"expected 0600, got {mode:o}"


def test_password_is_never_written(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    session_store.save("me@example.com", _tokens(), path)
    raw = path.read_text()
    assert "password" not in raw.lower()
    assert set(json.loads(raw)) == {
        "username", "id_token", "access_token", "refresh_token", "expires_at",
    }


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert session_store.load(tmp_path / "absent.json") is None


def test_corrupt_file_returns_none_rather_than_raising(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("{not json")
    assert session_store.load(path) is None


def test_incomplete_file_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"username": "me"}))
    assert session_store.load(path) is None


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "deeper" / "session.json"
    session_store.save("me@example.com", _tokens(), path)
    assert path.exists()


def test_clear_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    session_store.save("me@example.com", _tokens(), path)
    session_store.clear(path)
    session_store.clear(path)
    assert not path.exists()


def test_default_path_is_outside_any_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert session_store.default_path() == tmp_path / "pymysa" / "session.json"
