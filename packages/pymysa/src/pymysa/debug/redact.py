"""Redaction for capture bundles. See docs/specs/07-debug-harness.md.

Two passes. The first collects every device identifier in the bundle; the second scrubs,
replacing denied keys outright and rewriting identifiers wherever they appear - in dict
keys as well as values, which is how they leak if only exact values are matched.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

#: Anchored where a bare substring would catch a legitimate field: `city` matches
#: `capacity`, and `state` matches `drState` and `SwingState`.
#:
#: A pattern here is checked against the captured samples before it is added. `geofence`
#: was added on the assumption it carried a location and is a boolean feature flag
#: alongside `scheduling` and `zoning`; redacting it destroyed a protocol fact and hid
#: nothing.
DENY = re.compile(
    r"owner|allowedusers|^home$|homeid|email|^user(name)?$|token|credential|secret"
    r"|password|serial|pubkey|privkey|^mac$|ipaddress|^ip$|apikey|authorization"
    r"|postal|zipcode|^zip$|address|latitude|longitude|^city$|^province$|^country$"
    r"|^lat$|^lng$|^lon$",
    re.IGNORECASE,
)

IDENTIFIER = re.compile(r"^(deviceid|device|id|thingname)$", re.IGNORECASE)
NAME = re.compile(r"^name$", re.IGNORECASE)

# Values shaped like credentials, whatever key they arrive under.
SUSPECT_VALUE = re.compile(r"^(eyJ[\w-]{10,}|AKIA[0-9A-Z]{16}|arn:aws:)")

# A Mysa device id is a 12-character hex string.
DEVICE_ID = re.compile(r"\b[0-9a-f]{12}\b", re.IGNORECASE)

REVIEW_LENGTH = 64


class Redactor:
    def __init__(self) -> None:
        self._aliases: dict[str, str] = {}
        self.review: list[str] = []

    def device_alias(self, device_id: str) -> str:
        key = device_id.lower()
        if key not in self._aliases:
            digest = hashlib.sha256(key.encode()).hexdigest()[:8]
            self._aliases[key] = f"device-{digest}"
        return self._aliases[key]

    def scrub(self, value: Any, path: str = "") -> Any:
        """Collect identifiers, then rewrite. Safe to call on a whole bundle."""
        self._collect(value)
        return self._rewrite(value, path)

    # -- pass one -------------------------------------------------------------

    def _collect(self, value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if IDENTIFIER.match(key) and isinstance(item, str):
                    self.device_alias(item)
                # State payloads are keyed by device id, so keys leak too.
                for match in DEVICE_ID.findall(key):
                    self.device_alias(match)
                self._collect(item)
        elif isinstance(value, list):
            for item in value:
                self._collect(item)
        elif isinstance(value, str):
            for match in DEVICE_ID.findall(value):
                self.device_alias(match)

    # -- pass two -------------------------------------------------------------

    def _rewrite(self, value: Any, path: str) -> Any:
        if isinstance(value, dict):
            return {
                self._key(k): self._pair(k, v, f"{path}.{self._key(k)}")
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self._rewrite(v, f"{path}[]") for v in value]
        if isinstance(value, str):
            return self._string(value, path)
        return value

    def _key(self, key: str) -> str:
        return DEVICE_ID.sub(lambda m: self.device_alias(m.group(0)), key)

    def _pair(self, key: str, value: Any, path: str) -> Any:
        if DENY.search(key):
            return "<redacted>"
        if NAME.match(key) and isinstance(value, str):
            return "<device name>"
        return self._rewrite(value, path)

    def _string(self, value: str, path: str) -> str:
        if SUSPECT_VALUE.match(value):
            return "<redacted>"
        replaced = DEVICE_ID.sub(lambda m: self.device_alias(m.group(0)), value)
        if replaced == value and len(value) > REVIEW_LENGTH and path not in self.review:
            self.review.append(path)
        return replaced
