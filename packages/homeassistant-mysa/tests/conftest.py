"""Fixtures built from the captured payloads in `docs/samples`.

A test that hand-writes a device document tests the dictionary it just wrote. These are
redacted captures of real hardware, so an entity asserted against one is asserted
against what a device actually sends.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pymysa import MysaAccount, TransportError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mysa.const import (
    CONF_HOMES,
    CONF_REFRESH_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

SAMPLES = Path(__file__).parents[3] / "docs" / "samples"

BB_V1 = "BB-V1-0/read/device-728d8928.json"
BB_V1_NO_SCHEDULE = "BB-V1-0/read/device-f0e5a675.json"
BB_V3 = "BB-V3-0/read/device-42d6d24f.json"
AC_SWING = "AC-V1-0/read/device-c2c51c23.json"
AC_PLAIN = "AC-V1-0/read/device-1c4d5808.json"

HOME_ID = "id-57c49dd2"
SECOND_HOME = "id-second"

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant find `custom_components/mysa`."""
    return None


#: Patchers `setup_account` starts, ended by the fixture below. Only these: stopping
#: every patch in the process would take the test framework's own with them.
_PATCHERS: list[Any] = []


@pytest.fixture(autouse=True)
def stop_account_patches() -> Any:
    """End what `setup_account` started, once the test is done with it."""
    yield
    while _PATCHERS:
        _PATCHERS.pop().stop()


@dataclass
class Sample:
    """One captured device: its record, declaration, state and firmware answer."""

    record: dict[str, Any]
    capabilities: dict[str, Any]
    state: dict[str, Any]
    firmware: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.record["Id"])


def load(name: str, home: str = HOME_ID) -> Sample:
    """One `read` capture, as the SDK would have received it.

    Redaction replaced the home and the device name with placeholders, so both are put
    back here: every capture would otherwise be in the same home and called the same
    thing, and neither is a protocol fact.
    """
    payload = json.loads((SAMPLES / name).read_text())
    record = dict(payload["device"])
    record["Home"] = home
    record["Name"] = record["Id"]
    return Sample(
        record=record,
        capabilities=payload["capabilities"],
        state=payload["state"]["data"],
        firmware=payload["update_available"],
    )


HOMES = {
    "Homes": [
        {"Id": HOME_ID, "Name": "Home", "ERate": "0.0616"},
        {"Id": SECOND_HOME, "Name": "The Cabin"},
    ]
}


class FakeRest:
    """The transport, answering from the captures.

    A write lands in the section's `reported` half where `applies` allows it, which is
    what the SDK's confirmation reads back (spec 03). Where it does not, the write is
    the accepted-and-never-applied case.
    """

    def __init__(self, samples: list[Sample]) -> None:
        self.samples = {sample.id: sample for sample in samples}
        self.writes: list[tuple[str, dict[str, Any]]] = []
        self.state_reads = 0
        self.firmware_reads: list[str] = []
        self.applies = True
        self.refusal: Exception | None = None

    async def get_devices(self) -> dict[str, Any]:
        return {"DevicesObj": {i: s.record for i, s in self.samples.items()}}

    async def get_capabilities(self, device_id: str) -> dict[str, Any]:
        capabilities = self.samples[device_id].capabilities
        if "error" in capabilities:
            # An AC-V1-0 serves none: 404 for this app version (spec 04).
            raise TransportError(str(capabilities["error"]))
        return capabilities

    async def get_homes(self) -> dict[str, Any]:
        return HOMES

    async def get_schedules(self) -> dict[str, Any]:
        return {"Schedules": []}

    async def get_state_batch(self, device_ids: list[str]) -> dict[str, Any]:
        self.state_reads += 1
        return {
            device_id: {"data": self.samples[device_id].state}
            for device_id in device_ids
            if device_id in self.samples
        }

    async def get_update_available(self, device_id: str) -> dict[str, Any]:
        self.firmware_reads.append(device_id)
        return self.samples[device_id].firmware

    async def update_state(
        self, device_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.writes.append((device_id, payload))
        if self.refusal is not None:
            raise self.refusal
        if self.applies:
            self._apply(device_id, payload)
        return {"message": f"Successfully updated state for device {device_id}"}

    def _apply(self, device_id: str, payload: dict[str, Any]) -> None:
        state = self.samples[device_id].state
        for section, fields in payload.items():
            if section == "source" or not isinstance(fields, dict):
                continue
            body = state.setdefault(section, {})
            reported = body.setdefault("reported", {}) if "reported" in body else body
            reported.update(fields)


@dataclass
class Setup:
    """A configured entry and the transport behind it."""

    entry: MockConfigEntry
    rest: FakeRest
    accounts: list[MysaAccount] = field(default_factory=list)

    @property
    def account(self) -> MysaAccount:
        return self.accounts[-1]


def entry_for(homes: list[str] | None = None, password: str | None = None) -> MockConfigEntry:
    data = {CONF_USERNAME: "jamie@example.com", CONF_REFRESH_TOKEN: "refresh-token"}
    if password is not None:
        data[CONF_PASSWORD] = password
    return MockConfigEntry(
        domain=DOMAIN,
        title="jamie@example.com",
        unique_id="jamie@example.com",
        data=data,
        options={
            CONF_HOMES: homes if homes is not None else [HOME_ID],
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        },
    )


async def setup_account(
    hass: HomeAssistant,
    samples: list[Sample],
    entry: MockConfigEntry | None = None,
) -> Setup:
    """Set the integration up against a fake transport serving these captures."""
    entry = entry or entry_for()
    entry.add_to_hass(hass)
    rest = FakeRest(samples)
    result = Setup(entry=entry, rest=rest)

    def build(*args: Any, **kwargs: Any) -> MysaAccount:
        account = MysaAccount(*args, **kwargs)
        account.rest = rest  # type: ignore[assignment]
        result.accounts.append(account)
        return account

    # Started rather than scoped, so a reload inside the test builds its account from
    # the same transport. `stop_patches` ends it.
    patcher = patch("custom_components.mysa.coordinator.MysaAccount", side_effect=build)
    patcher.start()
    _PATCHERS.append(patcher)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return result


def hasten(setup: Setup) -> None:
    """Shorten the SDK's confirmation window to test length.

    A write is confirmed by polling until the value appears in `reported`, for eight
    seconds (spec 03). The window is a constructor default on the device object and the
    account builds its own devices, so a test that wants the outcome shortens it here.
    """
    for device in setup.account.devices.values():
        device._timeout = 0.2
        device._interval = 0.001


@pytest.fixture
def baseboards() -> list[Sample]:
    return [load(BB_V1), load(BB_V3)]


@pytest.fixture
def every_model() -> list[Sample]:
    return [load(BB_V1), load(BB_V3), load(AC_SWING), load(AC_PLAIN)]
