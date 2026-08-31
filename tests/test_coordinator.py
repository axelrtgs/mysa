"""Polling: what one clock does, and what happens when a poll fails."""

from __future__ import annotations

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pymysa import AuthenticationError, TransportError
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import BB_V1, BB_V3, Sample, load, setup_account

BASEBOARD = "climate.device_42d6d24f"


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: int) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_one_poll_covers_the_whole_account(
    hass: HomeAssistant, baseboards: list[Sample], freezer: FrozenDateTimeFactory
) -> None:
    """`refresh()` is one `/state/batch` for every discovered device (spec 09)."""
    setup = await setup_account(hass, baseboards)

    await _poll(hass, freezer, 61)

    assert setup.rest.state_reads == 2


async def test_a_new_reading_reaches_the_entity(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    setup = await setup_account(hass, [load(BB_V3)])
    assert hass.states.get(BASEBOARD).attributes["current_temperature"] == 23.7

    reading = setup.rest.samples["device-42d6d24f"].state["latestTelemetry"]["reading"]
    reading["roomTemperature"] = 19.2
    await _poll(hass, freezer, 61)

    assert hass.states.get(BASEBOARD).attributes["current_temperature"] == 19.2


async def test_a_failed_poll_makes_the_entities_unavailable(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    setup = await setup_account(hass, [load(BB_V3)])

    async def fail(device_ids: list[str]) -> dict[str, object]:
        raise TransportError("/state/batch returned 502")

    setup.rest.get_state_batch = fail  # type: ignore[method-assign]
    await _poll(hass, freezer, 61)

    assert hass.states.get(BASEBOARD).state == STATE_UNAVAILABLE


async def test_a_session_that_cannot_be_renewed_asks_the_user_to_sign_in(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    setup = await setup_account(hass, [load(BB_V3)])

    async def reject(device_ids: list[str]) -> dict[str, object]:
        raise AuthenticationError("/state/batch rejected the session token")

    setup.rest.get_state_batch = reject  # type: ignore[method-assign]
    await _poll(hass, freezer, 61)

    flows = hass.config_entries.flow.async_progress_by_handler("mysa")
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_firmware_is_not_read_on_every_poll(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """One request per device, for something that moves a few times a year (spec 06)."""
    setup = await setup_account(hass, [load(BB_V1)])
    assert setup.rest.firmware_reads == ["device-728d8928"]

    await _poll(hass, freezer, 61)
    assert setup.rest.firmware_reads == ["device-728d8928"]

    await _poll(hass, freezer, int(timedelta(hours=24).total_seconds()))
    assert setup.rest.firmware_reads == ["device-728d8928", "device-728d8928"]


async def test_a_device_that_cannot_report_a_critical_field_says_so(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A thermostat that cannot report its target temperature is broken whatever it is
    (spec 02); an unavailable entity with no explanation sends the user to their
    network."""
    sample = load(BB_V3)
    del sample.state["targetHeat"]

    await setup_account(hass, [sample])

    assert "device-42d6d24f (BB-V3-0) reports no target_temperature" in caplog.text


async def test_a_device_reporting_everything_says_nothing(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    await setup_account(hass, [load(BB_V3)])

    assert "reports no" not in caplog.text


async def test_a_poll_that_runs_long_fails_rather_than_stalling_the_entry(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A coordinator will not start a refresh while one is in flight, so a read with no
    deadline of its own stops the entry updating for as long as it hangs (spec 06)."""
    setup = await setup_account(hass, [load(BB_V3)])

    async def overrun(device_ids: list[str]) -> dict[str, object]:
        raise TimeoutError

    setup.rest.get_state_batch = overrun  # type: ignore[method-assign]
    await _poll(hass, freezer, 61)

    assert setup.entry.runtime_data.last_update_success is False
    assert hass.states.get(BASEBOARD).state == STATE_UNAVAILABLE
