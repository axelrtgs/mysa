"""Selects, switches, numbers and the hold button, against the captures."""

from __future__ import annotations

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.number import (
    ATTR_VALUE,
    SERVICE_SET_VALUE,
)
from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    Platform,
)
from homeassistant.core import HomeAssistant

from .conftest import AC_PLAIN, BB_V1, BB_V3, hasten, load, setup_account


async def test_the_lock_offers_three_states_where_the_device_declares_three(
    hass: HomeAssistant,
) -> None:
    """A BB-V3-0 declares 0, 1 and 3; the older model declares 0 and 3 (spec 04)."""
    await setup_account(hass, [load(BB_V3), load(BB_V1)])

    assert hass.states.get("select.device_42d6d24f_keypad_lock").attributes["options"] == [
        "unlocked",
        "limited to the lockout range",
        "full",
    ]
    assert hass.states.get("select.device_728d8928_keypad_lock").attributes["options"] == [
        "unlocked",
        "full",
    ]


async def test_the_lock_does_not_offer_an_ac_unit_a_state_it_never_reaches(
    hass: HomeAssistant,
) -> None:
    """It accepts a write of 1 and never applies it, in every mode tried (spec 02)."""
    await setup_account(hass, [load(AC_PLAIN)])

    options = hass.states.get("select.device_1c4d5808_keypad_lock").attributes["options"]
    assert options == ["unlocked", "full"]


async def test_selecting_a_named_option_writes_the_value_the_field_holds(
    hass: HomeAssistant,
) -> None:
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.device_42d6d24f_keypad_lock", ATTR_OPTION: "full"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert setup.rest.writes == [
        ("device-42d6d24f", {"source": 3, "physicalInterface": {"lockout": 3}})
    ]


async def test_a_field_the_device_declares_read_only_is_no_control(
    hass: HomeAssistant,
) -> None:
    """A BB-V1-0 reports `wakeOnApproach` and declares it read-only (spec 02)."""
    await setup_account(hass, [load(BB_V1), load(BB_V3)])

    assert hass.states.get("switch.device_728d8928_wake_on_approach") is None
    assert hass.states.get("switch.device_42d6d24f_wake_on_approach").state == STATE_OFF


async def test_the_proximity_switch_writes_the_flag(hass: HomeAssistant) -> None:
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)

    await hass.services.async_call(
        Platform.SWITCH,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.device_42d6d24f_wake_on_approach"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert setup.rest.writes == [
        ("device-42d6d24f", {"source": 3, "physicalInterface": {"wakeOnApproach": 1}})
    ]


async def test_setpoint_limits_exist_wherever_the_pair_is_reported(
    hass: HomeAssistant,
) -> None:
    """A BB-V1-0 carries the pair in `reported` alone and the app still moves it: the
    lockout pair is the exception to the desired-half rule (spec 02)."""
    await setup_account(hass, [load(BB_V3), load(BB_V1)])

    assert hass.states.get("number.device_42d6d24f_setpoint_minimum") is not None
    assert hass.states.get("number.device_728d8928_setpoint_minimum") is not None
    assert hass.states.get("number.device_728d8928_setpoint_maximum").state == "24"


async def test_a_setpoint_limit_is_bounded_by_the_declaration_not_by_itself(
    hass: HomeAssistant,
) -> None:
    """The lockout pair is 6-23 and the hardware range is 5-30; a limit bounded by the
    limit it replaces could only ever be narrowed (spec 09)."""
    await setup_account(hass, [load(BB_V3)])

    state = hass.states.get("number.device_42d6d24f_setpoint_minimum")
    assert (state.attributes["min"], state.attributes["max"]) == (5.0, 30.0)


async def test_writing_one_limit_carries_the_other_as_it_stands(
    hass: HomeAssistant,
) -> None:
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.device_42d6d24f_setpoint_minimum", ATTR_VALUE: 8},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert setup.rest.writes == [
        (
            "device-42d6d24f",
            {"source": 3, "targetHeat": {"lockoutMin": 8.0, "lockoutMax": 23}},
        )
    ]


async def test_brightness_writes_the_intensity_it_names(hass: HomeAssistant) -> None:
    """The capability document declares one brightness; the device reports two (spec 02)."""
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.device_42d6d24f_idle_brightness", ATTR_VALUE: 40},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert setup.rest.writes == [
        ("device-42d6d24f", {"source": 3, "physicalInterface": {"idleIntensity": 40}})
    ]


async def test_the_hold_is_released_and_never_started(hass: HomeAssistant) -> None:
    """Nothing observed starts a hold, so there is a button and not a switch (spec 08)."""
    setup = await setup_account(hass, [load(BB_V1)])
    hasten(setup)

    assert hass.states.get("switch.device_728d8928_schedule_hold") is None
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.device_728d8928_release_schedule_hold"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert setup.rest.writes == [
        ("device-728d8928", {"source": 3, "schedule": {"holding": False}})
    ]


async def test_adaptive_brightness_needs_the_document_and_not_the_desired_half(
    hass: HomeAssistant,
) -> None:
    """A BB-V1-0 carries `intensityMode` in `desired` and takes the write, and has no
    light sensor to act on it (spec 03)."""
    await setup_account(hass, [load(BB_V3), load(BB_V1)])

    assert hass.states.get("switch.device_42d6d24f_adaptive_brightness") is not None
    assert hass.states.get("switch.device_728d8928_adaptive_brightness") is None


async def test_adaptive_brightness_writes_the_intensity_mode(hass: HomeAssistant) -> None:
    setup = await setup_account(hass, [load(BB_V3)])
    hasten(setup)

    await hass.services.async_call(
        Platform.SWITCH,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.device_42d6d24f_adaptive_brightness"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert setup.rest.writes == [
        ("device-42d6d24f", {"source": 3, "physicalInterface": {"intensityMode": 0}})
    ]


async def test_climate_plus_is_an_ac_control(hass: HomeAssistant) -> None:
    """`modes.isThermostatic` is Climate+ in the app (spec 02)."""
    setup = await setup_account(hass, [load(AC_PLAIN), load(BB_V3)])
    hasten(setup)

    assert hass.states.get("switch.device_1c4d5808_climate") is not None
    await hass.services.async_call(
        Platform.SWITCH,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.device_1c4d5808_climate"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert setup.rest.writes == [
        ("device-1c4d5808", {"source": 3, "modes": {"isThermostatic": 0}})
    ]


async def test_the_release_button_comes_and_goes_with_the_hold(
    hass: HomeAssistant,
) -> None:
    """A button's state is the timestamp of its last press, so there is no history to
    keep by leaving one in place unavailable (spec 06)."""
    setup = await setup_account(hass, [load(BB_V1)])
    button = "button.device_728d8928_release_schedule_hold"
    assert hass.states.get(button) is not None
    assert hass.states.get("binary_sensor.device_728d8928_schedule_hold").state == "on"

    setup.rest.samples["device-728d8928"].state["schedule"]["holding"] = False
    await setup.account.refresh()
    setup.entry.runtime_data.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get(button) is None
    assert hass.states.get("binary_sensor.device_728d8928_schedule_hold").state == "off"


async def test_the_hold_sensor_stays_when_the_schedule_is_deleted(
    hass: HomeAssistant,
) -> None:
    """Deleting the schedule removes the section; the sensor keeps its history."""
    setup = await setup_account(hass, [load(BB_V1)])

    del setup.rest.samples["device-728d8928"].state["schedule"]
    await setup.account.refresh()
    setup.entry.runtime_data.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get("button.device_728d8928_release_schedule_hold") is None
    assert (
        hass.states.get("binary_sensor.device_728d8928_schedule_hold").state
        == "unavailable"
    )
    assert (
        hass.states.get("sensor.device_728d8928_next_schedule_event").state
        == "unavailable"
    )


async def test_a_hold_that_appears_brings_its_button_back(hass: HomeAssistant) -> None:
    setup = await setup_account(hass, [load(BB_V1)])
    button = "button.device_728d8928_release_schedule_hold"

    setup.rest.samples["device-728d8928"].state["schedule"]["holding"] = False
    await setup.account.refresh()
    setup.entry.runtime_data.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(button) is None

    setup.rest.samples["device-728d8928"].state["schedule"]["holding"] = True
    await setup.account.refresh()
    setup.entry.runtime_data.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get(button) is not None
