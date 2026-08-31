"""Writing to a device. See docs/specs/03-writes.md and docs/specs/09-sdk-surface.md.

A setter returns once the backend has accepted the write, with the written value held in
the cache as pending so a property read reflects it immediately. Confirmation runs in
the background: a write can return 200 and never appear in `reported`, and a caller that
treats 200 as success shows a value the device never took.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..exceptions import MysaError, UnsupportedCommand, ValueRefused
from ..meanings import value_for
from ..refusals import REJECTED, UNSUPPORTED_KIND, classify
from ..transport.rest import MysaRest
from ..writes import Write
from .maps import Source

_LOGGER = logging.getLogger(__name__)

#: How long a write has to appear in `reported` before it is treated as not applied.
CONFIRM_TIMEOUT = 8.0
CONFIRM_INTERVAL = 0.6


class Writing:
    """Setters and confirmation. Mixed into `MysaDevice`."""

    _rest: MysaRest
    _settings: dict[tuple[str, str], Any]
    _pending: dict[tuple[str, str], Any]
    _tasks: set[asyncio.Task[None]]
    _timeout: float
    _interval: float

    @property
    def id(self) -> str:  # pragma: no cover - supplied by MysaDevice
        raise NotImplementedError

    @property
    def model(self) -> str:  # pragma: no cover - supplied by MysaDevice
        raise NotImplementedError

    def _source(self, name: str) -> Source | None:  # pragma: no cover - MysaDevice
        raise NotImplementedError

    def update(self, document: dict[str, Any]) -> None:  # pragma: no cover
        raise NotImplementedError

    @property
    def active_setpoint(self) -> str:  # pragma: no cover - Readings
        raise NotImplementedError

    def _write_failed(self, field: str, value: Any) -> None:  # pragma: no cover
        raise NotImplementedError

    # Writes.

    async def set_mode(self, mode: str) -> None:
        await self._set("mode", mode)

    async def set_temperature(self, celsius: float, *, wait: bool = False) -> None:
        """Write the setpoint the current mode selects (spec 03)."""
        await self._set(self.active_setpoint, celsius, wait=wait)

    async def set_heat_setpoint(self, celsius: float, *, wait: bool = False) -> None:
        await self._set("target_temperature", celsius, wait=wait)

    async def set_cool_setpoint(self, celsius: float, *, wait: bool = False) -> None:
        await self._set("target_temperature_cool", celsius, wait=wait)

    async def set_setpoint_limits(self, low: float, high: float) -> None:
        source = self._source(self.active_setpoint)
        if source is None:
            raise UnsupportedCommand(f"{self.model} reports no setpoint to bound")
        await self._write(source.section, {"lockoutMin": low, "lockoutMax": high})

    async def set_fan_speed(self, speed: str) -> None:
        await self._set("fan_speed", speed)

    async def set_vertical_swing(self, position: str) -> None:
        await self._set("vertical_swing", position)

    async def set_horizontal_swing(self, position: str) -> None:
        await self._set("horizontal_swing", position)

    async def set_lock(self, state: str) -> None:
        await self._set("lock", state)

    async def set_proximity(self, on: bool) -> None:
        await self._set("proximity", 1 if on else 0)

    async def set_temperature_format(self, unit: str) -> None:
        await self._set("temperature_format", unit)

    async def set_brightness(
        self, active: int | None = None, idle: int | None = None
    ) -> None:
        """Both display intensities. The capability document declares them as one."""
        fields: dict[str, Any] = {}
        if active is not None:
            fields["activeIntensity"] = active
        if idle is not None:
            fields["idleIntensity"] = idle
        if not fields:
            return
        await self._write("physicalInterface", fields)

    async def _set(self, name: str, value: Any, *, wait: bool = False) -> None:
        source = self._source(name)
        if source is None:
            raise UnsupportedCommand(f"{self.model} does not report {name}")
        wire = value_for(source.section, source.field, value, self.model)
        self._check(source, name, wire)
        await self._write(source.section, {source.field: wire}, wait=wait)

    def _check(self, source: Source, name: str, wire: Any) -> None:
        """Refuse locally what the device's own declaration refuses silently.

        A value outside the declared set is accepted with 200 and never applied
        (spec 04), which a caller cannot tell from a device that declined.
        """
        setting = self._settings.get((source.section, source.field))
        if setting is None:
            return
        if not setting.writable:
            raise UnsupportedCommand(f"{self.model} does not allow writing {name}")
        if not setting.values:
            return
        # The declaration can name values the field holds as numbers, so it is
        # translated before anything is compared to it (spec 04).
        allowed = [
            value_for(source.section, source.field, value, self.model)
            for value in setting.values
        ]
        if wire not in allowed:
            names = ", ".join(repr(value) for value in setting.values)
            raise ValueRefused(f"{name} takes one of {names}, not {wire!r}")

    async def _write(
        self, section: str, fields: dict[str, Any], *, wait: bool = False
    ) -> None:
        try:
            await self._rest.update_state(self.id, Write(section, fields).payload())
        except MysaError as err:
            kind, reason = classify(str(err))
            if kind == UNSUPPORTED_KIND:
                raise UnsupportedCommand(reason) from err
            if kind == REJECTED:
                raise ValueRefused(reason) from err
            raise

        for field, value in fields.items():
            self._pending[(section, field)] = value
        if wait:
            await self._confirm(section, fields)
            return
        task = asyncio.create_task(self._confirm(section, fields))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _confirm(self, section: str, fields: dict[str, Any]) -> None:
        """Poll until the device carries the written values, then settle the cache.

        A write can return 200 and never appear in `reported` (spec 03). Dropping the
        pending value puts the property back to what the device actually holds.
        """
        deadline = asyncio.get_running_loop().time() + self._timeout
        outstanding = dict(fields)
        while outstanding:
            await asyncio.sleep(self._interval)
            try:
                batch = await self._rest.get_state_batch([self.id])
            except MysaError:
                _LOGGER.debug("%s: confirmation read failed", self.id, exc_info=True)
                batch = {}
            entry = batch.get(self.id)
            data = entry.get("data") if isinstance(entry, dict) else None
            if isinstance(data, dict):
                self.update(data)
            outstanding = {
                field: value
                for field, value in outstanding.items()
                if (section, field) in self._pending
            }
            if asyncio.get_running_loop().time() >= deadline:
                break

        for field, value in outstanding.items():
            self._pending.pop((section, field), None)
            _LOGGER.info(
                "%s: %s.%s was accepted and not applied", self.id, section, field
            )
            self._write_failed(f"{section}.{field}", value)
