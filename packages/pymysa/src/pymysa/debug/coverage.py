"""Choosing which devices to write to.

A write run takes minutes per device. Two units of the same model, firmware and section
set answer the same questions, so one stands for the other.

Model and firmware alone are not a configuration: two AC-V1-0 on one account run the same
firmware and differ in the sections they carry, and collapsing those would leave the
difference untested.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Configuration:
    model: str
    firmware: str
    sections: tuple[str, ...]

    def describe(self) -> str:
        return f"{self.model} fw {self.firmware}, {len(self.sections)} section(s)"


def configuration(record: dict[str, Any], document: dict[str, Any]) -> Configuration:
    identity = document.get("identity", {})
    reported = identity.get("reported") if isinstance(identity, dict) else None
    reported = reported if isinstance(reported, dict) else {}
    return Configuration(
        model=reported.get("model") or record.get("Model", "?"),
        firmware=reported.get("fw") or "?",
        sections=tuple(sorted(document)),
    )


def representatives(
    devices: dict[str, dict[str, Any]], documents: dict[str, dict[str, Any]]
) -> dict[str, list[str]]:
    """Device id to exercise, mapped to the ids it stands for.

    The representative is the lowest id in its group, so repeated runs cover the same
    unit and its samples accumulate against one baseline.
    """
    groups: dict[Configuration, list[str]] = {}
    for device_id in sorted(devices):
        config = configuration(devices[device_id], documents.get(device_id, {}))
        groups.setdefault(config, []).append(device_id)
    return {members[0]: members[1:] for members in groups.values()}
