"""Homes. See docs/specs/02-devices.md.

A home carries the account's electricity rate, which is the only value in the payload
the SDK names: address and zones are account administration, not device state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Home:
    """One entry from `/homes`."""

    id: str
    name: str | None
    #: Cost per kilowatt hour, as the account has it set. Served as a string.
    electricity_rate: float | None
    raw: dict[str, Any]

    @classmethod
    def parse(cls, entry: dict[str, Any]) -> Home:
        return cls(
            id=str(entry.get("Id", "")),
            name=entry.get("Name"),
            electricity_rate=_rate(entry.get("ERate")),
            raw=entry,
        )


def parse_homes(payload: dict[str, Any]) -> dict[str, Home]:
    entries = payload.get("Homes") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return {}
    homes = [Home.parse(e) for e in entries if isinstance(e, dict)]
    return {home.id: home for home in homes if home.id}


def _rate(value: Any) -> float | None:
    """`ERate` is served as a string. A rate that will not parse is not a rate."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
