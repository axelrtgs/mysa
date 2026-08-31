"""The account's only clock. See docs/specs/06-ha-entities.md.

The SDK holds state and owns no timer (spec 09), so one coordinator per config entry
polls `/state/batch` for every device the entry includes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pymysa import AuthenticationError, MysaAccount, MysaAuth, MysaDevice, MysaError

from .const import DOMAIN, FIRMWARE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type MysaConfigEntry = ConfigEntry[MysaCoordinator]

#: Critical semantic names (spec 02) and how to read each one. `connected` is absent:
#: a device reporting no connection state reads the same as one reporting itself
#: offline, and the connectivity entity is what says which (spec 06).
CRITICAL: dict[str, Callable[[MysaDevice], float | None]] = {
    "current_temperature": lambda device: device.current_temperature,
    "target_temperature": lambda device: device.target_temperature,
    "mode": lambda device: device.mode_value,
}


class MysaCoordinator(DataUpdateCoordinator[None]):
    """Discovers once, then polls the account."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MysaConfigEntry,
        auth: MysaAuth,
        session: aiohttp.ClientSession,
        homes: list[str] | None,
        interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.account = MysaAccount(
            auth, session, on_write_failed=self._write_failed, homes=homes
        )
        self._firmware_read: float | None = None

    async def _async_setup(self) -> None:
        """Identity and capability, once: what exists and what it can do (spec 09)."""
        try:
            await self.account.discover()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MysaError as err:
            raise UpdateFailed(f"discovery failed: {err}") from err
        for device_id, reason in self.account.unavailable.items():
            _LOGGER.warning("%s could not be read and is not set up: %s", device_id, reason)

    async def _async_update_data(self) -> None:
        try:
            await self.account.refresh()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MysaError as err:
            raise UpdateFailed(f"state read failed: {err}") from err
        await self._maybe_refresh_firmware()

    async def _maybe_refresh_firmware(self) -> None:
        now = dt_util.utcnow().timestamp()
        if (
            self._firmware_read is not None
            and now - self._firmware_read < FIRMWARE_INTERVAL.total_seconds()
        ):
            return
        self._firmware_read = now
        try:
            await self.account.refresh_firmware()
        except MysaError as err:
            # Not a failed poll: the state read has already succeeded.
            _LOGGER.debug("firmware read failed: %s", err)

    def report_missing(self) -> None:
        """Log the critical fields a device does not report, once per setup (spec 05)."""
        for device in self.account.devices.values():
            missing = [name for name, read in CRITICAL.items() if read(device) is None]
            if missing:
                _LOGGER.error(
                    "%s (%s) reports no %s; its climate entity cannot work from what "
                    "it sends",
                    device.name,
                    device.model,
                    ", ".join(missing),
                )

    @callback
    def _write_failed(self, device: MysaDevice, field: str, value: Any) -> None:
        """A write the backend accepted and the device never applied (spec 03).

        The SDK has already dropped the pending value, so updating the listeners puts
        every entity back to what the device actually holds.
        """
        _LOGGER.warning(
            "%s accepted %s=%r and did not apply it; the value shown is back to what "
            "the device reports",
            device.name,
            field,
            value,
        )
        self.async_update_listeners()
