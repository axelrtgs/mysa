"""Signing in and picking devices, shared by the commands."""

from __future__ import annotations

import argparse
from typing import Any

import aiohttp

from ..exceptions import MysaError
from ..transport.rest import MysaRest
from .auth import authenticate, prompt


async def collect(
    args: argparse.Namespace, http: aiohttp.ClientSession
) -> tuple[MysaRest, dict[str, Any], list[str]]:
    auth = await authenticate(args, http)
    rest = MysaRest(auth, http)
    devices = (await rest.get_devices()).get("DevicesObj", {})
    if not devices:
        raise MysaError("no devices on this account")
    ids = [args.device] if args.device else sorted(devices)
    missing = [d for d in ids if d not in devices]
    if missing:
        raise MysaError(f"not on this account: {', '.join(missing)}")
    return rest, devices, ids


async def choose(devices: dict[str, Any], ids: list[str]) -> str:
    """Pick a device interactively when a command needs exactly one."""
    print("\nDevices:")
    for index, device_id in enumerate(ids, 1):
        record = devices[device_id]
        print(f"  {index}. {record.get('Name', '?')}  [{record.get('Model', '?')}]")
    while True:
        raw = await prompt("Select a device: ")
        if raw.isdigit() and 1 <= int(raw) <= len(ids):
            return ids[int(raw) - 1]
        print("  not a listed number")
