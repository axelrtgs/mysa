"""An account and the devices on it. See docs/specs/09-sdk-surface.md.

The SDK holds state and the caller drives refresh. Nothing here runs a timer: the
transport is poll-only, so there is nothing to push, and a caller that already polls -
Home Assistant's coordinator does - would be running a second one.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import aiohttp

from .auth import MysaAuth
from .devices import MysaDevice
from .exceptions import MysaError
from .homes import Home, parse_homes
from .schedules import Schedule, parse_schedules
from .transport.rest import MysaRest

_LOGGER = logging.getLogger(__name__)


class MysaAccount:
    """Every device the account can see, and the last state read for them."""

    def __init__(
        self,
        auth: MysaAuth,
        session: aiohttp.ClientSession,
        *,
        owns_session: bool = False,
        on_write_failed: Callable[[MysaDevice, str, Any], None] | None = None,
        homes: Iterable[str] | None = None,
    ) -> None:
        self._auth = auth
        self._session = session
        self._owns_session = owns_session
        self._on_write_failed = on_write_failed
        self.rest = MysaRest(auth, session)
        self._devices: dict[str, MysaDevice] = {}
        self._schedules: tuple[Schedule, ...] = ()
        self._homes: dict[str, Home] = {}
        self._included: frozenset[str] | None = None if homes is None else frozenset(homes)
        self.unavailable: dict[str, str] = {}

    @classmethod
    async def login(
        cls,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
        **kwargs: Any,
    ) -> MysaAccount:
        """Authenticate and return an account ready to discover.

        The password is used once, for the SRP exchange. What is kept afterwards is the
        refresh token (spec 01).
        """
        owns = session is None
        session = session or aiohttp.ClientSession()
        auth = MysaAuth(username, password, session=session)
        await auth.id_token()
        return cls(auth, session, owns_session=owns, **kwargs)

    @property
    def devices(self) -> Mapping[str, MysaDevice]:
        return self._devices

    @property
    def schedules(self) -> tuple[Schedule, ...]:
        return self._schedules

    @property
    def homes(self) -> Mapping[str, Home]:
        return self._homes

    @property
    def included_homes(self) -> frozenset[str] | None:
        """The homes discovery is limited to, or None for every home."""
        return self._included

    async def list_homes(self) -> Mapping[str, Home]:
        """The account's homes, without discovering any device.

        One request. A caller choosing which homes to take - an integration asking at
        setup - needs the list before it commits to discovering anything.
        """
        self._homes = parse_homes(await self.rest.get_homes())
        return self._homes

    def limit_to(self, home_ids: Iterable[str] | None) -> None:
        """Take only devices in these homes. None takes every home.

        Applies from the next `discover()`, which drops the devices it now excludes;
        `refresh()` reads only what discovery kept, so an excluded device is not polled.
        """
        self._included = None if home_ids is None else frozenset(home_ids)
        if self._included is not None and self._homes:
            unknown = sorted(self._included - set(self._homes))
            if unknown:
                _LOGGER.warning(
                    "no home on this account has the id %s", ", ".join(unknown)
                )

    def home_of(self, device: MysaDevice) -> Home | None:
        """The home a device belongs to, where discovery could read it."""
        return self._homes.get(device.home_id or "")

    async def discover(self) -> Mapping[str, MysaDevice]:
        """What exists and what it can do: records, capabilities, homes, schedules.

        A device whose capability document cannot be read is discovered without one - an
        AC-V1-0 returns 404 for it (spec 04) and is a working device. One whose record
        cannot be read at all is omitted and named in `unavailable`.
        """
        records = self._included_records(_records(await self.rest.get_devices()))
        for device_id, record in records.items():
            try:
                capabilities = await self._capabilities(device_id)
            except MysaError as err:
                self.unavailable[device_id] = str(err)
                continue
            self.unavailable.pop(device_id, None)
            existing = self._devices.get(device_id)
            if existing is not None:
                existing.adopt(record, capabilities)
                continue
            self._devices[device_id] = MysaDevice(
                record, self.rest, capabilities=capabilities,
                on_write_failed=self._on_write_failed,
            )

        for gone in set(self._devices) - set(records):
            device = self._devices.pop(gone)
            await device.aclose()

        self._schedules = await self._optional(self.rest.get_schedules, parse_schedules, ())
        self._homes = await self._optional(self.rest.get_homes, parse_homes, {})
        return self._devices

    async def refresh(self) -> Mapping[str, MysaDevice]:
        """One `/state/batch` for every discovered device."""
        if not self._devices:
            return self._devices
        batch = await self.rest.get_state_batch(list(self._devices))
        for device_id, device in self._devices.items():
            entry = batch.get(device_id)
            data = entry.get("data") if isinstance(entry, dict) else None
            if isinstance(data, dict):
                device.update(data)
            else:
                _LOGGER.debug("%s: absent from the state batch", device_id)
        return self._devices

    def _included_records(
        self, records: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Records in the homes discovery is limited to.

        A device whose record names no home is in no home, and a caller that asked for
        one home did not ask for it.
        """
        if self._included is None:
            return records
        return {
            device_id: record
            for device_id, record in records.items()
            if record.get("Home") in self._included
        }

    async def _capabilities(self, device_id: str) -> dict[str, Any] | None:
        """The structured declaration, or None where the device serves none."""
        try:
            return await self.rest.get_capabilities(device_id)
        except MysaError as err:
            _LOGGER.debug("%s: no capability document (%s)", device_id, err)
            return None

    async def _optional(self, call: Any, parse: Any, default: Any) -> Any:
        """A discovery read whose failure is not a failed discovery.

        Devices are what discovery is for; homes and schedules are context.
        """
        try:
            return parse(await call())
        except MysaError as err:
            _LOGGER.debug("optional discovery read failed: %s", err)
            return default

    async def aclose(self) -> None:
        """Cancel confirmations, then close what this account opened."""
        await asyncio.gather(*(d.aclose() for d in self._devices.values()))
        await self._auth.aclose()
        if self._owns_session:
            await self._session.close()


def _records(payload: Any) -> dict[str, dict[str, Any]]:
    """Device records from `/devices`, keyed by id.

    The endpoint returns `DevicesObj` keyed by device id, and older captures carry a
    `Devices` array alongside it.
    """
    if not isinstance(payload, dict):
        return {}
    keyed = payload.get("DevicesObj")
    if isinstance(keyed, dict):
        return {k: v for k, v in keyed.items() if isinstance(v, dict)}
    listed = payload.get("Devices")
    if isinstance(listed, list):
        return {
            str(entry["Id"]): entry
            for entry in listed
            if isinstance(entry, dict) and entry.get("Id")
        }
    return {}
