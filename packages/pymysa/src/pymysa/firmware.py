"""Firmware update availability. See docs/specs/09-sdk-surface.md.

`/devices/update_available` reports what a device is running and what the backend would
give it. No install path has been observed on any surface this project reads, so this is
an answer and not a control.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FirmwareUpdate:
    """What the backend says about one device's firmware."""

    available: bool
    installed: str | None
    allowed: str | None

    @classmethod
    def parse(cls, payload: Any) -> FirmwareUpdate | None:
        """None where the endpoint answered with anything but an answer.

        A BB-V3-0 returns 500 for its own device (spec 09). An unknown answer is not the
        same as no update, so nothing is defaulted here.
        """
        if not isinstance(payload, dict):
            return None
        available = payload.get("update")
        if not isinstance(available, bool):
            return None
        return cls(
            available=available,
            installed=_version(payload.get("installedVersion")),
            allowed=_version(payload.get("allowedVersion")),
        )


def _version(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
