"""Setting the entry up, and what each model produces."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .conftest import (
    AC_SWING,
    BB_V1,
    BB_V1_NO_SCHEDULE,
    BB_V3,
    SECOND_HOME,
    Sample,
    load,
    setup_account,
)


def _entities(hass: HomeAssistant, device_id: str) -> set[str]:
    registry = er.async_get(hass)
    return {
        entry.unique_id.removeprefix(f"{device_id}-")
        for entry in registry.entities.values()
        if entry.unique_id == device_id or entry.unique_id.startswith(f"{device_id}-")
    }


async def test_the_entry_sets_up_and_polls_once(
    hass: HomeAssistant, baseboards: list[Sample]
) -> None:
    setup = await setup_account(hass, baseboards)

    assert setup.entry.state is ConfigEntryState.LOADED
    assert setup.rest.state_reads == 1
    assert set(setup.account.devices) == {"device-728d8928", "device-42d6d24f"}


async def test_a_device_becomes_one_registry_entry(hass: HomeAssistant) -> None:
    await setup_account(hass, [load(BB_V3)])

    device = dr.async_get(hass).async_get_device(identifiers={("mysa", "device-42d6d24f")})
    assert device is not None
    assert device.manufacturer == "Mysa"
    assert device.model == "BB-V3-0"
    assert device.sw_version == "5.1.9"


async def test_a_baseboard_reporting_no_serial_still_registers(hass: HomeAssistant) -> None:
    """A BB-V1-0's identity carries family, fw and model only (spec 02)."""
    await setup_account(hass, [load(BB_V1)])

    device = dr.async_get(hass).async_get_device(identifiers={("mysa", "device-728d8928")})
    assert device is not None
    assert device.serial_number is None


async def test_the_climate_entity_keeps_the_device_id_as_its_unique_id(
    hass: HomeAssistant,
) -> None:
    await setup_account(hass, [load(BB_V1)])

    registry = er.async_get(hass)
    assert registry.async_get_entity_id("climate", "mysa", "device-728d8928")


async def test_a_baseboard_exposes_its_electrical_readings(hass: HomeAssistant) -> None:
    await setup_account(hass, [load(BB_V3)])

    keys = _entities(hass, "device-42d6d24f")
    assert {"current", "voltage", "power", "duty_cycle", "energy"} <= keys


async def test_an_ac_unit_exposes_no_power_or_energy(hass: HomeAssistant) -> None:
    """AC units report no `power` section and no energy (spec 02, spec 05)."""
    await setup_account(hass, [load(AC_SWING)])

    keys = _entities(hass, "device-c2c51c23")
    assert "voltage" in keys
    assert {"current", "power", "energy", "duty_cycle"} & keys == set()


async def test_a_bb_v3_reports_no_signal_strength(hass: HomeAssistant) -> None:
    """Its telemetry reading carries no rssi (spec 02)."""
    await setup_account(hass, [load(BB_V3), load(BB_V1)])

    assert "signal_strength" not in _entities(hass, "device-42d6d24f")
    assert "signal_strength" in _entities(hass, "device-728d8928")


async def test_the_schedule_entities_follow_the_section_and_not_the_model(
    hass: HomeAssistant,
) -> None:
    """One BB-V1-0 carries a schedule section and the other does not (spec 02)."""
    await setup_account(hass, [load(BB_V1), load(BB_V1_NO_SCHEDULE)])

    assert "release_hold" in _entities(hass, "device-728d8928")
    assert "release_hold" not in _entities(hass, "device-f0e5a675")


async def test_the_electricity_rate_comes_from_the_home(hass: HomeAssistant) -> None:
    await setup_account(hass, [load(BB_V1)])

    state = hass.states.get("sensor.device_728d8928_electricity_rate")
    assert state is not None
    assert state.state == "0.0616"


async def test_a_device_in_a_home_the_entry_excludes_is_never_discovered(
    hass: HomeAssistant,
) -> None:
    """`limit_to` runs before discovery, so an excluded device is not polled either."""
    setup = await setup_account(
        hass, [load(BB_V1), load(BB_V3, home=SECOND_HOME)]
    )

    assert set(setup.account.devices) == {"device-728d8928"}
    assert setup.rest.state_reads == 1
    assert not _entities(hass, "device-42d6d24f")


async def test_firmware_is_read_once_per_setup(
    hass: HomeAssistant, baseboards: list[Sample]
) -> None:
    setup = await setup_account(hass, baseboards)

    assert setup.rest.firmware_reads == ["device-728d8928", "device-42d6d24f"]


async def test_the_firmware_entity_exists_only_where_the_endpoint_answered(
    hass: HomeAssistant, baseboards: list[Sample]
) -> None:
    """A BB-V3-0 returns 500 for its own update check (spec 09)."""
    await setup_account(hass, baseboards)

    assert "firmware_update" in _entities(hass, "device-728d8928")
    assert "firmware_update" not in _entities(hass, "device-42d6d24f")


async def test_unloading_stops_the_entry(
    hass: HomeAssistant, baseboards: list[Sample]
) -> None:
    setup = await setup_account(hass, baseboards)
    reads = setup.rest.state_reads

    assert await hass.config_entries.async_unload(setup.entry.entry_id)
    await hass.async_block_till_done()

    assert setup.entry.state is ConfigEntryState.NOT_LOADED
    assert setup.rest.state_reads == reads
    for entity_id in hass.states.async_entity_ids("climate"):
        assert hass.states.is_state(entity_id, "unavailable")


async def test_a_disconnected_device_still_reports_that_it_is_disconnected(
    hass: HomeAssistant,
) -> None:
    """The entity whose job is to say the device is offline cannot go unavailable for
    being offline."""
    sample = load(BB_V3)
    sample.state["latestTelemetry"]["isConnected"] = False

    await setup_account(hass, [sample])

    assert hass.states.get("binary_sensor.device_42d6d24f_connection").state == "off"
    assert hass.states.get("climate.device_42d6d24f").state == "unavailable"
