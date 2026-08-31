"""Reading a device through its field map, and what it declares."""

from __future__ import annotations

from pymysa.capabilities import Capability
from pymysa.devices import MysaDevice

BB_V3_DOC = {
    "identity": {"reported": {"model": "BB-V3-0", "fw": "5.1.9", "serial": "SCR34NRTZN"}},
    "latestTelemetry": {
        "isConnected": True,
        "reading": {"roomTemperature": 23.7, "humidity": 47, "energy": 0, "dutyCycle": 0},
    },
    "targetHeat": {
        "desired": {"setpoint": 16, "lockoutMin": 6, "lockoutMax": 23},
        "reported": {"setpoint": 16, "lockoutMin": 6, "lockoutMax": 23},
    },
    "modes": {"desired": {"mode": 0}, "reported": {"mode": 0}},
    "physicalInterface": {
        "desired": {"lockout": 0, "format": "C", "wakeOnApproach": 0, "intensityMode": 1},
        "reported": {"lockout": 0, "format": "C", "wakeOnApproach": 0, "intensityMode": 1},
    },
    "power": {"reported": {"current": 0, "voltage": 240, "wattage": 0, "dutyCycle": 0}},
    "cloudFeatures": {"cloudEarlyOn": {"enabled": True}},
}

BB_V3_CAPABILITIES = {
    "features": {
        "climateControl": {"mode": {"userControllable": True, "type": "enum",
                                    "validValues": ["off", "heat"]}},
        "interface": {
            "lockout": {"userControllable": True, "type": "integer",
                        "validValues": [0, 1, 3]},
            "wakeOnApproach": {"userControllable": True, "type": "boolean"},
            "unit": {"userControllable": True, "type": "enum", "validValues": ["C", "F"]},
        },
        "sensing": {"temperature": {"trackingSensor": {
            "userControllable": True, "type": "enum", "validValues": ["internal", "remote"]}}},
    }
}

AC_DOC = {
    "identity": {"reported": {"model": "AC-V1-0", "fw": "3.17.5.9"}},
    "latestTelemetry": {"isConnected": True, "reading": {"roomTemperature": 21.5, "rssi": -45}},
    "targetHeat": {"desired": {"setpoint": 21}, "reported": {"setpoint": 21}},
    "targetCool": {"desired": {"setpoint": 20}, "reported": {"setpoint": 20}},
    "modes": {
        "desired": {"mode": 3, "fan_mode": 0, "verticalSwingState": 2},
        "reported": {"mode": 3, "fan_mode": 0, "verticalSwingState": 2, "unitPower": 2},
    },
}


class NoRest:
    async def update_state(self, device_id, payload):
        raise AssertionError("no write expected")

    async def get_state_batch(self, ids):
        return {}


def _device(record, document, capabilities=None):
    device = MysaDevice(record, NoRest(), capabilities=capabilities)
    device.update(document)
    return device


def bb_v3(**kwargs):
    return _device({"Id": "9070", "Name": "Living Room", "Model": "BB-V3-0"},
                   BB_V3_DOC, BB_V3_CAPABILITIES, **kwargs)


def ac(record=None):
    return _device(record or {"Id": "a4e5", "Name": "Hallway", "Model": "AC-V1-0"}, AC_DOC)


def test_values_come_from_the_models_own_field_map():
    device = bb_v3()

    assert device.current_temperature == 23.7
    assert device.target_temperature == 16
    assert device.wattage == 0
    assert device.serial == "SCR34NRTZN"


def test_a_field_the_model_does_not_report_is_none():
    """Absent is not zero, and nothing is defaulted from another model's document."""
    device = bb_v3()

    assert device.fan_speed is None
    assert device.signal_strength is None          # a BB-V3-0 reports no rssi
    assert device.duty_cycle == 0                  # reported, and zero


def test_a_model_with_no_field_map_reads_nothing():
    """A model nobody has described reports what it reports and the SDK names none of it."""
    document = {**BB_V3_DOC, "identity": {"reported": {"model": "XX-V9-0"}}}
    device = _device({"Id": "x", "Model": "XX-V9-0"}, document)

    assert device.current_temperature is None
    assert device.capabilities == frozenset()


def test_an_enumerated_value_is_exposed_by_name_and_by_value():
    device = bb_v3()

    assert device.mode == "off"
    assert device.mode_value == 0


def test_an_unmapped_value_keeps_its_number():
    """A name nobody has established is not a reason to hide the value."""
    document = {**BB_V3_DOC, "modes": {"reported": {"mode": 42}}}
    device = _device({"Id": "9070", "Model": "BB-V3-0"}, document, BB_V3_CAPABILITIES)

    assert device.mode is None
    assert device.mode_value == 42


def test_a_nested_value_is_read_through_its_key():
    assert bb_v3().early_on is True


def test_the_active_setpoint_follows_the_mode():
    """A unit carrying both applies the one its mode selects (spec 03)."""
    device = ac()

    assert device.mode == "cool"
    assert device.active_setpoint == "target_temperature_cool"
    assert device.target_temperature == 20
    assert device.heat_setpoint == 21


def test_the_active_setpoint_falls_back_to_heat_where_there_is_only_one():
    device = bb_v3()

    assert device.active_setpoint == "target_temperature"


def test_a_read_only_control_is_not_a_capability():
    """A BB-V1-0 reports wakeOnApproach and its document declares it read-only."""
    capabilities = {"features": {"interface": {
        "wakeOnApproach": {"userControllable": False, "type": "boolean"}}}}
    document = {**BB_V3_DOC, "identity": {"reported": {"model": "BB-V1-0"}}}
    device = _device({"Id": "3c71", "Model": "BB-V1-0"}, document, capabilities)

    assert device.proximity is False              # reported
    assert not device.supports(Capability.PROXIMITY)


def test_a_writable_control_is_a_capability():
    assert bb_v3().supports(Capability.PROXIMITY)


def test_a_control_with_one_option_is_not_declared():
    """A BB-V1-0 declares trackingSensor writable with `internal` as its only value."""
    capabilities = {"features": {"sensing": {"temperature": {"trackingSensor": {
        "userControllable": True, "type": "enum", "validValues": ["internal"]}}}}}
    document = {**BB_V3_DOC, "tracking": {"desired": {"tracking": 0},
                                          "reported": {"tracking": 0}}}
    device = _device({"Id": "9070", "Model": "BB-V3-0"}, document, capabilities)

    assert not device.supports(Capability.SENSOR_MODE)


def test_options_no_map_can_translate_are_not_offered():
    """`trackingSensor` declares names for a field holding 0; the write is refused."""
    document = {**BB_V3_DOC, "tracking": {"desired": {"tracking": 0},
                                          "reported": {"tracking": 0}}}
    device = _device({"Id": "9070", "Model": "BB-V3-0"}, document, BB_V3_CAPABILITIES)

    assert not device.supports(Capability.SENSOR_MODE)
    assert device.options(Capability.SENSOR_MODE) == ()


def test_declared_names_are_translated_before_being_offered():
    """The document declares mode as off and heat; the field holds 0 and 4."""
    assert bb_v3().modes == ("off", "heat")


def test_the_reported_mode_is_always_offered():
    document = {**BB_V3_DOC, "modes": {"reported": {"mode": 7}}}
    device = _device({"Id": "9070", "Model": "BB-V3-0"}, document, BB_V3_CAPABILITIES)

    assert device.modes == ("off", "heat", "fan only")


def test_an_ac_without_a_capability_document_offers_what_it_has_been_seen_to_take():
    device = ac()

    assert device.modes == ("off", "auto", "cool", "heat", "fan only", "dry")
    assert device.options(Capability.FAN) == ("auto", "low", "medium", "high")


def test_a_control_the_codeset_cannot_express_is_not_declared():
    """A unit reports horizontalSwingState whether or not its remote has the control."""
    record = {"Id": "ac67", "Model": "AC-V1-0", "SupportedCaps": {"keys": [8, 9, 10, 11, 47]}}
    document = {**AC_DOC, "modes": {
        "desired": {"mode": 3, "fan_mode": 0, "verticalSwingState": 2, "horizontalSwingState": 1},
        "reported": {"mode": 3, "fan_mode": 0, "verticalSwingState": 2, "horizontalSwingState": 1},
    }}
    device = _device(record, document)

    assert device.supports(Capability.FAN)
    assert device.supports(Capability.VERTICAL_SWING)
    assert not device.supports(Capability.HORIZONTAL_SWING)


def test_a_field_with_no_desired_half_is_not_a_control():
    """The backend holds no desired value for unitPower, so a write is dropped."""
    device = ac()

    assert device.unit_power == 2
    assert not device._controls("unit_power")


def test_identity_survives_an_empty_document():
    device = MysaDevice({"Id": "9070", "Name": "Living Room", "Model": "BB-V3-0"}, NoRest())

    assert device.id == "9070"
    assert device.name == "Living Room"
    assert device.model == "BB-V3-0"
    assert device.available is False
    assert device.current_temperature is None


async def test_setting_the_temperature_writes_the_section_the_mode_selects():
    """An AC in cool applies targetCool and ignores a targetHeat write (spec 03)."""

    class Recorder(NoRest):
        def __init__(self):
            self.writes: list[tuple[str, dict]] = []

        async def update_state(self, device_id, payload):
            section = next(k for k in payload if k != "source")
            self.writes.append((section, dict(payload[section])))
            return {"message": "ok"}

        async def get_state_batch(self, ids):
            return {ids[0]: {"data": AC_DOC}}

    rest = Recorder()
    device = MysaDevice({"Id": "a4e5", "Model": "AC-V1-0"}, rest, timeout=0.05, interval=0.01)
    device.update(AC_DOC)

    await device.set_temperature(22, wait=True)

    assert rest.writes == [("targetCool", {"setpoint": 22})]
