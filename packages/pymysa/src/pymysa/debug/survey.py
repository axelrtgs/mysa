"""Everything the account will tell us about a device, and what is new in it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeviceSurvey:
    device_id: str
    name: str
    model: str
    firmware: str
    connected: bool | None
    sections: dict[str, list[str]] = field(default_factory=dict)

    def describe(self) -> str:
        state = {True: "online", False: "offline", None: "unknown"}[self.connected]
        return (
            f"{self.name} [{self.model} fw {self.firmware}] {state} - "
            f"{len(self.sections)} section(s), "
            f"{sum(len(v) for v in self.sections.values())} field(s)"
        )


def survey(
    device_id: str, record: dict[str, Any], document: dict[str, Any]
) -> DeviceSurvey:
    """Catalogue one device's state document and flag anything uncatalogued."""
    telemetry = document.get("latestTelemetry", {})
    identity = _half(document.get("identity", {}))

    result = DeviceSurvey(
        device_id=device_id,
        name=record.get("Name", "?"),
        model=identity.get("model") or record.get("Model", "?"),
        firmware=identity.get("fw") or "?",
        connected=telemetry.get("isConnected") if isinstance(telemetry, dict) else None,
    )

    for section, body in document.items():
        result.sections[section] = sorted(_fields(body))
        if section == "latestTelemetry" and isinstance(body, dict):
            reading = body.get("reading")
            if isinstance(reading, dict):
                result.sections["latestTelemetry.reading"] = sorted(reading)
    return result


def _half(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    half = body.get("reported")
    return half if isinstance(half, dict) else body


def _fields(body: Any) -> set[str]:
    if not isinstance(body, dict):
        return set()
    found: set[str] = set()
    for half in ("reported", "desired"):
        if isinstance(body.get(half), dict):
            found |= set(body[half])
    return found or set(body)
