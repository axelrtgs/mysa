"""The thermostat, per model, against the captures."""

from __future__ import annotations

import pytest
from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_HVAC_MODE,
    ATTR_SWING_MODE,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .conftest import AC_PLAIN, AC_SWING, BB_V1, BB_V3, Sample, hasten, load, setup_account

BASEBOARD = "climate.device_42d6d24f"
AC = "climate.device_1c4d5808"
AC_WITH_SWING = "climate.device_c2c51c23"


def _in_mode(sample: Sample, mode: int) -> Sample:
    """The same capture with the unit in another mode."""
    sample.state["modes"]["reported"]["mode"] = mode
    return sample


async def test_a_baseboard_offers_the_modes_it_declares_not_the_ones_it_accepts(
    hass: HomeAssistant,
) -> None:
    """A BB-V3-0 accepts 0, 1, 3, 4, 5 and 6 and declares off and heat (spec 02)."""
    await setup_account(hass, [load(BB_V3)])

    state = hass.states.get(BASEBOARD)
    assert state is not None
    assert state.attributes["hvac_modes"] == [HVACMode.OFF, HVACMode.HEAT]


async def test_an_ac_unit_offers_every_mode_it_has_been_seen_to_apply(
    hass: HomeAssistant,
) -> None:
    """It serves no capability document (spec 04), so the observed set is what there is."""
    await setup_account(hass, [load(AC_PLAIN)])

    state = hass.states.get(AC)
    assert state is not None
    assert state.attributes["hvac_modes"] == [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.FAN_ONLY,
        HVACMode.DRY,
    ]


async def test_a_mode_value_nothing_names_is_neither_offered_nor_reported(
    hass: HomeAssistant,
) -> None:
    """5 and 6 are values a BB-V3-0 takes and nothing has been seen to select."""
    await setup_account(hass, [_in_mode(load(BB_V3), 5)])

    state = hass.states.get(BASEBOARD)
    assert state is not None
    assert state.state == "unknown"
    assert HVACMode.OFF in state.attributes["hvac_modes"]


async def test_the_setpoint_bounds_follow_the_mode_on_a_unit_with_two_sections(
    hass: HomeAssistant,
) -> None:
    """`targetCool` carries no lockout pair; 19-24 is the heat section's (spec 09)."""
    await setup_account(hass, [load(AC_PLAIN), _in_mode(load(AC_SWING), 4)])

    cooling = hass.states.get(AC)
    heating = hass.states.get(AC_WITH_SWING)
    assert cooling is not None and heating is not None
    assert (cooling.attributes["min_temp"], cooling.attributes["max_temp"]) == (16.0, 30.0)
    assert (heating.attributes["min_temp"], heating.attributes["max_temp"]) == (19.0, 24.0)


async def test_a_baseboard_is_bounded_by_its_own_lockout_pair(hass: HomeAssistant) -> None:
    await setup_account(hass, [load(BB_V3), load(BB_V1)])

    baseboard = hass.states.get(BASEBOARD)
    older = hass.states.get("climate.device_728d8928")
    assert baseboard is not None and older is not None
    assert (baseboard.attributes["min_temp"], baseboard.attributes["max_temp"]) == (6.0, 23.0)
    assert (older.attributes["min_temp"], older.attributes["max_temp"]) == (5.0, 24.0)
    assert baseboard.attributes["target_temp_step"] == 0.5


async def test_swing_is_offered_where_the_codeset_declares_it(hass: HomeAssistant) -> None:
    await setup_account(hass, [load(AC_SWING)])

    state = hass.states.get(AC_WITH_SWING)
    assert state is not None
    assert state.attributes["swing_modes"] == ["off", "on"]
    assert state.attributes["fan_modes"] == ["auto", "low", "medium", "high"]
    assert state.attributes["supported_features"] & ClimateEntityFeature.SWING_MODE


async def test_horizontal_swing_is_not_offered_for_being_reported(
    hass: HomeAssistant,
) -> None:
    """The unit reports `horizontalSwingState` and declines every write to it: what the
    codeset can express is what the unit has, and the state document is not the
    declaration (spec 04)."""
    await setup_account(hass, [load(AC_SWING)])

    state = hass.states.get(AC_WITH_SWING)
    assert state is not None
    assert state.state == HVACMode.COOL
    assert state.attributes.get("swing_horizontal_modes") is None
    assert not state.attributes["supported_features"] & (
        ClimateEntityFeature.SWING_HORIZONTAL_MODE
    )


async def test_a_baseboard_has_no_fan_or_swing_at_all(hass: HomeAssistant) -> None:
    await setup_account(hass, [load(BB_V3)])

    state = hass.states.get(BASEBOARD)
    assert state is not None
    assert state.attributes.get("fan_modes") is None
    assert state.attributes.get("swing_modes") is None
    assert not state.attributes["supported_features"] & (
        ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE
    )


async def test_a_setpoint_write_goes_to_the_section_the_mode_selects(
    hass: HomeAssistant,
) -> None:
    """On a unit holding mode 3, the cool setpoint applies and the heat one does not
    (spec 03)."""
    setup = await setup_account(hass, [load(AC_PLAIN)])
    hasten(setup)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: AC, ATTR_TEMPERATURE: 23},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert setup.rest.writes == [
        ("device-1c4d5808", {"source": 3, "targetCool": {"setpoint": 23.0}})
    ]


async def test_a_baseboard_setpoint_goes_to_the_heat_section(hass: HomeAssistant) -> None:
    setup = await setup_account(hass, [_in_mode(load(BB_V3), 4)])
    hasten(setup)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: BASEBOARD, ATTR_TEMPERATURE: 18.5},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert setup.rest.writes == [
        ("device-42d6d24f", {"source": 3, "targetHeat": {"setpoint": 18.5}})
    ]
    assert hass.states.get(BASEBOARD).attributes[ATTR_TEMPERATURE] == 18.5


async def test_a_mode_is_written_as_the_number_the_field_holds(hass: HomeAssistant) -> None:
    """The capability document declares names; the state field holds integers (spec 04)."""
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: BASEBOARD, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert setup.rest.writes == [("device-42d6d24f", {"source": 3, "modes": {"mode": 4}})]
    assert hass.states.get(BASEBOARD).state == HVACMode.HEAT


async def test_fan_and_swing_are_written_by_name_and_land_as_numbers(
    hass: HomeAssistant,
) -> None:
    setup = await setup_account(hass, [load(AC_SWING)])
    hasten(setup)

    for service, key, value in (
        (SERVICE_SET_FAN_MODE, ATTR_FAN_MODE, "high"),
        (SERVICE_SET_SWING_MODE, ATTR_SWING_MODE, "off"),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            service,
            {ATTR_ENTITY_ID: AC_WITH_SWING, key: value},
            blocking=True,
        )
    await hass.async_block_till_done()

    assert setup.rest.writes == [
        ("device-c2c51c23", {"source": 3, "modes": {"fan_mode": 3}}),
        ("device-c2c51c23", {"source": 3, "modes": {"verticalSwingState": 1}}),
    ]


async def test_a_setpoint_is_refused_while_the_thermostat_is_off(
    hass: HomeAssistant,
) -> None:
    """The device does not act on it and the app will not let you set one (spec 03)."""
    setup = await setup_account(hass, [load(BB_V3)])

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: BASEBOARD, ATTR_TEMPERATURE: 21},
            blocking=True,
        )

    assert setup.rest.writes == []
