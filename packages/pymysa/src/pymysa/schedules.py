"""Schedules, as far as they are established. See docs/specs/08-schedules.md.

Read-only, plus one write. A device's `schedule` section says whether a schedule is in
force and when it next acts; `/schedules` lists the definitions the account holds, whose
event encoding is not established and is therefore not parsed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .transport.rest import MysaRest
from .writes import Write


@dataclass(frozen=True)
class Schedule:
    """One entry from `/schedules`, identified by its contents.

    The array comes back in a different order on each read, so nothing keys off its
    position, and an entry carries no id of its own: `Device` is what identifies it.

    `actions` is the `ScheduledActions` map, keyed by weekday name. Every capture has
    empty day lists, so what an event inside one looks like is not established and
    nothing here parses it (spec 08).
    """

    device_id: str | None
    actions: dict[str, Any]
    raw: dict[str, Any]

    @property
    def days(self) -> tuple[str, ...]:
        return tuple(self.actions)

    @property
    def empty(self) -> bool:
        return not any(self.actions.values())

    @classmethod
    def parse(cls, entry: dict[str, Any]) -> Schedule:
        actions = entry.get("ScheduledActions")
        return cls(
            device_id=entry.get("Device"),
            actions=actions if isinstance(actions, dict) else {},
            raw=entry,
        )


def parse_schedules(payload: dict[str, Any]) -> tuple[Schedule, ...]:
    entries = payload.get("Schedules")
    if not isinstance(entries, list):
        return ()
    return tuple(Schedule.parse(e) for e in entries if isinstance(e, dict))


class ScheduleHold:
    """A device's hold state.

    Exists only while a schedule is assigned: the section is absent otherwise, and
    `holding` and `resolved` read as absent again once the schedule is deleted.
    """

    def __init__(self, device_id: str, body: dict[str, Any], rest: MysaRest) -> None:
        self._device_id = device_id
        self._body = body
        self._rest = rest

    @property
    def holding(self) -> bool | None:
        value = self._body.get("holding")
        return None if value is None else bool(value)

    @property
    def resolved(self) -> bool | None:
        value = self._body.get("resolved")
        return None if value is None else bool(value)

    @property
    def next_event(self) -> datetime | None:
        """When the hold ends, or the next scheduled change. Absent while held open."""
        value = self._body.get("nextEvent")
        if not isinstance(value, (int, float)):
            return None
        return datetime.fromtimestamp(value, tz=UTC)

    async def release(self) -> None:
        """End the hold and follow the schedule again.

        One-way. Ending a hold is a write; nothing observed starts one, and the field
        reads as absent afterwards rather than as false (spec 08).
        """
        await self._rest.update_state(
            self._device_id, Write("schedule", {"holding": False}).payload()
        )
        self._body["holding"] = False

    def __repr__(self) -> str:
        return f"<ScheduleHold {self._device_id} holding={self.holding}>"
