"""Signing in, and caching the session so a password is asked for once."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

import aiohttp

from .. import session_store
from ..auth import MysaAuth
from ..exceptions import AuthenticationError


async def prompt(message: str) -> str:
    """Read one line without blocking the loop."""
    return (await asyncio.to_thread(input, message)).strip()


async def authenticate(
    args: argparse.Namespace, http: aiohttp.ClientSession
) -> MysaAuth:
    """Reuse a cached session when possible; prompt only when it cannot be used."""
    cache = args.session or session_store.default_path()

    if not args.login:
        cached = session_store.load(cache)
        if cached is not None:
            username, tokens = cached
            auth = MysaAuth(username, session=http)
            auth.restore(tokens)
            try:
                await auth.id_token()
            except AuthenticationError as err:
                print(f"cached session unusable ({err}); signing in again")
            else:
                print(f"using cached session for {username}")
                persist(auth, cache)
                return auth

    username = os.environ.get("MYSA_USERNAME") or await prompt("Mysa email: ")
    password = os.environ.get("MYSA_PASSWORD") or await asyncio.to_thread(
        getpass.getpass, "Mysa password: "
    )
    auth = MysaAuth(username, password, session=http)
    await auth.login()
    persist(auth, cache)
    return auth


def persist(auth: MysaAuth, cache: Path) -> None:
    tokens = auth.tokens
    if tokens is None:
        return
    try:
        session_store.save(auth.username, tokens, cache)
    except OSError as err:
        print(f"could not write session cache: {err}", file=sys.stderr)
