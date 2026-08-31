"""What a setpoint write may contain. See docs/specs/09-sdk-surface.md."""

from __future__ import annotations

from pymysa.capabilities import Capability
from pymysa.devices import MysaDevice

BB_CAPABILITIES = {
    "features": {
        "climateControl": {
            "heat": {"setpoint": {"userControllable": True, "type": "float",
                                  "validValues": [5, 5.5, 6, 29.5, 30]}},
        }
    }
}

AC_RECORD = {"Id": "a4e5", "Model": "AC-V1-0", "SupportedCaps": {"tempRange": [16, 30]}}

AC_DOC = {
    "identity": {"reported": {"model": "AC-V1-0"}},
    "latestTelemetry": {"isConnected": True, "reading": {"roomTemperature": 21.5}},
    "targetHeat": {"desired": {"setpoint": 21},
                   "reported": {"setpoint": 21, "lockoutMin": 19, "lockoutMax": 24}},
    "targetCool": {"desired": {"setpoint": 21}, "reported": {"setpoint": 21}},
    "modes": {"desired": {"mode": 3}, "reported": {"mode": 3}},
}


class NoRest:
    async def update_state(self, device_id, payload):
        raise AssertionError("no write expected")


def _device(record, document, capabilities=None):
    device = MysaDevice(record, NoRest(), capabilities=capabilities)
    device.update(document)
    return device


def _bb(document, capabilities=None):
    return _device({"Id": "9070", "Model": "BB-V3-0"}, document, capabilities)


def _bb_document(**setpoint):
    return {
        "identity": {"reported": {"model": "BB-V3-0"}},
        "latestTelemetry": {"isConnected": True, "reading": {"roomTemperature": 23.7}},
        "targetHeat": {"desired": {"setpoint": 16}, "reported": {"setpoint": 16, **setpoint}},
        "modes": {"desired": {"mode": 0}, "reported": {"mode": 0}},
    }


def test_the_section_the_mode_selects_supplies_its_own_bounds():
    device = _bb(_bb_document(lockoutMin=6, lockoutMax=23), BB_CAPABILITIES)

    assert device.setpoint_range == (6.0, 23.0)


def test_the_declaration_is_the_fallback_where_the_section_reports_no_lockout():
    """The lockout pair is a setting; a device without one still has a range."""
    device = _bb(_bb_document(), BB_CAPABILITIES)

    assert device.setpoint_range == (5.0, 30.0)


def test_a_device_that_declares_nothing_and_reports_no_lockout_has_no_range():
    assert _bb(_bb_document()).setpoint_range is None


def test_a_cool_setpoint_is_bounded_by_the_codeset_and_not_by_the_heat_lockout():
    """`targetCool` carries no lockout pair, and 19-24 is the heat section's limit."""
    device = _device(AC_RECORD, AC_DOC)

    assert device.active_setpoint == "target_temperature_cool"
    assert device.setpoint_range == (16.0, 30.0)


def test_a_heat_setpoint_on_the_same_unit_is_bounded_by_its_lockout():
    document = {**AC_DOC, "modes": {"desired": {"mode": 4}, "reported": {"mode": 4}}}
    device = _device(AC_RECORD, document)

    assert device.active_setpoint == "target_temperature"
    assert device.setpoint_range == (19.0, 24.0)


def test_a_declared_range_stands_where_the_section_is_absent_from_the_document():
    """The declaration describes the device, not the poll that has just come back."""
    document = {"identity": {"reported": {"model": "BB-V3-0"}},
                "latestTelemetry": {"isConnected": True, "reading": {}}}

    assert _bb(document, BB_CAPABILITIES).setpoint_range == (5.0, 30.0)


def test_a_lockout_pair_with_one_half_missing_is_not_a_range():
    device = _bb(_bb_document(lockoutMin=6), BB_CAPABILITIES)

    assert device.setpoint_range == (5.0, 30.0)


def test_every_model_is_written_at_half_a_degree():
    assert _bb(_bb_document()).setpoint_step == 0.5
    assert _device(AC_RECORD, AC_DOC).setpoint_step == 0.5


def test_the_lockout_pair_is_writable_where_it_is_reported_only():
    """A BB-V1-0 carries it in `reported` alone and the app moves both (spec 02)."""
    document = _bb_document(lockoutMin=5, lockoutMax=24)
    document["targetHeat"]["desired"] = {"setpoint": 20}
    device = _bb(document, BB_CAPABILITIES)

    assert Capability.SETPOINT_LIMITS in device.capabilities
    assert (device.min_setpoint, device.max_setpoint) == (5, 24)


def test_a_device_reporting_no_lockout_pair_declares_no_limits():
    assert Capability.SETPOINT_LIMITS not in _bb(_bb_document()).capabilities
