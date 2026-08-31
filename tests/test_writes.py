"""The write path: what the user sees, and what happens when the device declines."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.components.climate import (
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pymysa import TransportError

from .conftest import BB_V3, hasten, load, setup_account

BASEBOARD = "climate.device_42d6d24f"

VALIDATION = TransportError(
    '/state/device-42d6d24f/update returned 400: {"statusCode": 400, '
    '"code": "FST_ERR_VALIDATION", "error": "Bad Request", '
    '"message": "body/targetHeat/setpoint must be >= 5"}'
)

CAPABILITY = TransportError(
    '/state/device-42d6d24f/update returned 400: {"error": "Failed to validate request '
    'body", "message": ["Wake on approach is not supported"]}'
)


async def _set_temperature(hass: HomeAssistant, value: float) -> None:
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: BASEBOARD, ATTR_TEMPERATURE: value},
        blocking=True,
    )


async def test_the_written_value_shows_before_the_next_poll(hass: HomeAssistant) -> None:
    """The setter returns once the backend accepts it, with the value already readable
    from the device (spec 09)."""
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)
    setup.rest.applies = False

    await _set_temperature(hass, 21)

    assert hass.states.get(BASEBOARD).attributes[ATTR_TEMPERATURE] == 21.0
    await hass.async_block_till_done()


async def test_a_value_the_device_declares_invalid_is_refused_without_a_request(
    hass: HomeAssistant,
) -> None:
    """A BB-V3-0 declares its setpoint at half degrees, and the backend accepts anything
    else with 200 and never applies it (spec 04). Refusing locally is what tells the
    difference."""
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)

    with pytest.raises(ServiceValidationError):
        await _set_temperature(hass, 18.7)

    assert setup.rest.writes == []
    assert hass.states.get(BASEBOARD).attributes[ATTR_TEMPERATURE] == 16


async def test_a_schema_refusal_reaches_the_user_as_a_bad_value(
    hass: HomeAssistant,
) -> None:
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)
    setup.rest.refusal = VALIDATION

    with pytest.raises(ServiceValidationError) as refused:
        await _set_temperature(hass, 21)

    assert "must be >= 5" in str(refused.value)


async def test_a_capability_refusal_reaches_the_user_as_a_missing_feature(
    hass: HomeAssistant,
) -> None:
    """The backend stating the device does not have the feature is a fact about the
    device, not a malformed request (spec 03)."""
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)
    setup.rest.refusal = CAPABILITY

    with pytest.raises(ServiceValidationError) as refused:
        await _set_temperature(hass, 21)

    assert "Wake on approach is not supported" in str(refused.value)


async def test_a_transport_failure_is_not_a_refusal(hass: HomeAssistant) -> None:
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)
    setup.rest.refusal = TransportError("update request failed: connection reset")

    with pytest.raises(HomeAssistantError) as failed:
        await _set_temperature(hass, 21)

    assert not isinstance(failed.value, ServiceValidationError)


async def test_a_write_that_is_accepted_and_never_applied_snaps_back(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The confirmation drops the pending value and calls `on_write_failed`; the
    integration puts every entity back to what the device reports (spec 06)."""
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)
    setup.rest.applies = False

    await _set_temperature(hass, 21)
    assert hass.states.get(BASEBOARD).attributes[ATTR_TEMPERATURE] == 21.0

    await asyncio.sleep(0.3)
    await hass.async_block_till_done()

    assert hass.states.get(BASEBOARD).attributes[ATTR_TEMPERATURE] == 16
    assert "accepted targetHeat.setpoint=21.0 and did not apply it" in caplog.text
