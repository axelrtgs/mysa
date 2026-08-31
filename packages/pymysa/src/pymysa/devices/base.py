"""A device as the SDK exposes it. See docs/specs/09-sdk-surface.md.

A device is a live view of the account's cache, not a snapshot: the same object reflects
the next refresh. It holds no timer and fetches nothing on its own.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from ..capabilities import declared, settings
from ..confirm import close
from ..firmware import FirmwareUpdate
from ..meanings import name_of
from ..schedules import ScheduleHold
from ..transport.rest import MysaRest
from .declaration import Declaration
from .maps import FIELDS, READING, RECORD, TELEMETRY, Source
from .readings import Readings
from .writing import CONFIRM_INTERVAL, CONFIRM_TIMEOUT, Writing


class MysaDevice(Readings, Declaration, Writing):
    """One device. Built by `MysaAccount`; not constructed directly by a caller."""

    def __init__(
        self,
        record: dict[str, Any],
        rest: MysaRest,
        *,
        capabilities: dict[str, Any] | None = None,
        on_write_failed: Callable[[MysaDevice, str, Any], None] | None = None,
        timeout: float = CONFIRM_TIMEOUT,
        interval: float = CONFIRM_INTERVAL,
    ) -> None:
        self._record = record
        self._rest = rest
        self._document: dict[str, Any] = {}
        self._pending: dict[tuple[str, str], Any] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._settings = settings(capabilities)
        self._declared = declared(record.get("SupportedCaps"))
        self._capability_document = capabilities
        self._on_write_failed = on_write_failed
        self._firmware_update: FirmwareUpdate | None = None
        self._timeout = timeout
        self._interval = interval

    # Identity.

    @property
    def id(self) -> str:
        return str(self._record.get("Id", ""))

    @property
    def name(self) -> str:
        return str(self._record.get("Name", self.id))

    @property
    def model(self) -> str:
        return str(self._section("identity").get("model") or self._record.get("Model", ""))

    @property
    def home_id(self) -> str | None:
        home = self._record.get("Home")
        return str(home) if home else None

    @property
    def firmware(self) -> str | None:
        return self._text("firmware")

    @property
    def serial(self) -> str | None:
        return self._text("serial")

    @property
    def available(self) -> bool:
        """Whether the device reports itself connected. Unknown reads as unavailable."""
        return bool(self._value("connected"))

    @property
    def firmware_update(self) -> FirmwareUpdate | None:
        """The last update answer, or None until `refresh_firmware()` reads one."""
        return self._firmware_update

    @property
    def raw(self) -> dict[str, Any]:
        """The device's own state document, for a field the SDK does not name."""
        return self._document

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.id} {self.name!r} {self.model}>"

    # Cache.

    def adopt(self, record: dict[str, Any], capabilities: dict[str, Any] | None) -> None:
        """Take a fresh record and declaration, keeping the object a caller holds.

        A renamed device, or one whose firmware changed what it declares, is the same
        device: replacing the object would strand whatever is subscribed to it.
        """
        self._record = record
        self._settings = settings(capabilities)
        self._declared = declared(record.get("SupportedCaps"))
        self._capability_document = capabilities

    def adopt_firmware(self, payload: dict[str, Any] | None) -> None:
        """Take an `/devices/update_available` answer.

        An unreadable one leaves the last answer in place: a device the endpoint cannot
        answer for has an unknown state, which is not a device with no update.
        """
        update = FirmwareUpdate.parse(payload)
        if update is not None:
            self._firmware_update = update

    def update(self, document: dict[str, Any]) -> None:
        """Take a new state document. Pending writes that have landed are dropped."""
        self._document = document
        for key in list(self._pending):
            if close(self._reported(*key), self._pending[key]):
                del self._pending[key]

    def _section(self, name: str) -> dict[str, Any]:
        """The values in force in a section, shadow pair or not."""
        if name == RECORD:
            return self._record
        if name == READING:
            telemetry = self._document.get(TELEMETRY)
            reading = telemetry.get("reading") if isinstance(telemetry, dict) else None
            return reading if isinstance(reading, dict) else {}
        body = self._document.get(name)
        if not isinstance(body, dict):
            return {}
        half = body.get("reported")
        return half if isinstance(half, dict) else body

    def _reported(self, section: str, field: str) -> Any:
        return self._section(section).get(field)

    def _source(self, name: str) -> Source | None:
        return FIELDS.get(self.model, {}).get(name)

    def _value(self, name: str) -> Any:
        source = self._source(name)
        if source is None:
            return None
        pending = self._pending.get((source.section, source.field))
        value = pending if pending is not None else self._reported(source.section, source.field)
        if source.nested:
            return value.get(source.nested) if isinstance(value, dict) else None
        return value

    def _number(self, name: str) -> float | None:
        """A measured or set quantity. A non-numeric value is not a number."""
        value = self._value(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value

    def _integer(self, name: str) -> int | None:
        value = self._value(name)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    def _flag(self, name: str) -> bool | None:
        value = self._value(name)
        return None if value is None else bool(value)

    def _text(self, name: str) -> str | None:
        value = self._value(name)
        return value if isinstance(value, str) else None

    def _named(self, name: str) -> str | None:
        source = self._source(name)
        if source is None:
            return None
        return name_of(source.section, source.field, self._value(name), self.model)

    @property
    def schedule(self) -> ScheduleHold | None:
        """Hold state, or None where no schedule is assigned to this device."""
        body = self._document.get("schedule")
        if not isinstance(body, dict):
            return None
        return ScheduleHold(self.id, body, self._rest)

    def _write_failed(self, field: str, value: Any) -> None:
        if self._on_write_failed is not None:
            self._on_write_failed(self, field, value)

    async def aclose(self) -> None:
        """Cancel confirmations still in flight."""
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
