"""On-disk session cache.

Stores the Cognito refresh token so repeated runs do not need a password. The file lives
outside the repository by default, which is stronger than relying on .gitignore: it
cannot be committed by accident at all.

Never stores the password.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .auth import Tokens

_LOGGER = logging.getLogger(__name__)

FILE_MODE = 0o600
DIR_MODE = 0o700


def default_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "pymysa" / "session.json"


def load(path: Path | None = None) -> tuple[str, Tokens] | None:
    """Return (username, tokens) when a usable cache exists."""
    path = path or default_path()
    try:
        raw: dict[str, Any] = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as err:
        _LOGGER.warning("ignoring unreadable session cache %s: %s", path, err)
        return None

    try:
        return raw["username"], Tokens(
            id_token=raw["id_token"],
            access_token=raw["access_token"],
            refresh_token=raw["refresh_token"],
            expires_at=float(raw["expires_at"]),
        )
    except (KeyError, TypeError, ValueError):
        _LOGGER.warning("ignoring malformed session cache %s", path)
        return None


def save(username: str, tokens: Tokens, path: Path | None = None) -> Path:
    path = path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    payload = {
        "username": username,
        "id_token": tokens.id_token,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": tokens.expires_at,
    }
    # Create with restrictive permissions before any content is written.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(payload, handle)
    os.chmod(path, FILE_MODE)
    return path


def clear(path: Path | None = None) -> None:
    path = path or default_path()
    path.unlink(missing_ok=True)
