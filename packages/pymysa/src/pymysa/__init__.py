"""Python SDK for Mysa smart thermostats. See docs/specs/09-sdk-surface.md."""

from __future__ import annotations

from .account import MysaAccount
from .auth import MysaAuth
from .capabilities import Capability
from .devices import MysaDevice
from .exceptions import (
    AuthenticationError,
    MysaError,
    TransportError,
    UnsupportedCommand,
    ValueRefused,
)
from .firmware import FirmwareUpdate
from .homes import Home
from .schedules import Schedule, ScheduleHold

__version__ = "0.2.0"

__all__ = [
    "AuthenticationError",
    "Capability",
    "FirmwareUpdate",
    "Home",
    "MysaAccount",
    "MysaAuth",
    "MysaDevice",
    "MysaError",
    "Schedule",
    "ScheduleHold",
    "TransportError",
    "UnsupportedCommand",
    "ValueRefused",
]
