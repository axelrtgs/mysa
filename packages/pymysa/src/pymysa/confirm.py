"""Read-after-write confirmation.

A write is confirmed when a read returns the value that was written. The shadow's
`reported` half is the value in force; `latestTelemetry.reading` carries the device's
own copy of the same field on its reporting cadence, so where the two can be compared a
disagreement means the write has not reached the hardware yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Shadow field to the telemetry field holding the device's own copy. [observed]
TELEMETRY_MIRROR = {
    ("targetHeat", "setpoint"): "heatSetpoint",
    ("targetCool", "setpoint"): "coolSetpoint",
    ("modes", "mode"): "mode",
}


@dataclass(frozen=True)
class Confirmation:
    section: str
    field: str
    expected: Any
    after: float | None = None
    observed: Any = None
    telemetry: Any = None

    @property
    def confirmed(self) -> bool:
        return self.after is not None

    def describe(self) -> str:
        target = f"{self.section}.{self.field}"
        if not self.confirmed:
            return f"{target}: not confirmed; read back {self.observed!r}"
        line = f"{target} = {self.expected!r} confirmed after {self.after:.1f}s"
        if self.telemetry is not None and not close(self.telemetry, self.expected):
            line += f"; device telemetry still reports {self.telemetry!r}"
        return line


def sections(batch: dict[str, Any], device_id: str) -> dict[str, dict[str, Any]]:
    """Every section of one device's `/state/batch` entry, shadow pair or not."""
    entry = batch.get(device_id)
    if not isinstance(entry, dict):
        return {}
    return {
        name: body
        for name, body in entry.get("data", {}).items()
        if isinstance(body, dict)
    }


def shadow(batch: dict[str, Any], device_id: str, section: str) -> dict[str, Any] | None:
    """Sections carrying `desired` and `reported`. Others have neither."""
    body = sections(batch, device_id).get(section)
    if not isinstance(body, dict) or ("reported" not in body and "desired" not in body):
        return None
    return body


def in_force(batch: dict[str, Any], device_id: str, section: str, field: str) -> Any:
    """The value a device holds.

    `schedule` and `cloudFeatures` are flat: the section is the value in force. Reading
    only shadow pairs returns None for them, and every confirmation against that section
    then fails whatever the device did.
    """
    body = sections(batch, device_id).get(section)
    if not isinstance(body, dict):
        return None
    half = body.get("reported")
    source = half if isinstance(half, dict) else body
    return source.get(field)


def telemetry_value(batch: dict[str, Any], device_id: str, section: str, field: str) -> Any:
    """The device's own copy of a field, where one exists."""
    name = TELEMETRY_MIRROR.get((section, field))
    if name is None:
        return None
    entry = batch.get(device_id)
    if not isinstance(entry, dict):
        return None
    reading = entry.get("data", {}).get("latestTelemetry", {}).get("reading")
    return reading.get(name) if isinstance(reading, dict) else None


def close(value: Any, expected: Any) -> bool:
    """Numeric compare with tolerance; the cloud may round what we sent."""
    if isinstance(value, (int, float)) and isinstance(expected, (int, float)):
        return abs(float(value) - float(expected)) < 0.051
    return bool(value == expected)
