"""Controls an AC codeset declares."""

from __future__ import annotations

from pymysa.capabilities import FAN, HORIZONTAL_SWING, VERTICAL_SWING, declared, gates


def test_a_modes_block_declares_the_controls_it_lists():
    caps = {"modes": {"4": {"fanSpeeds": [1, 2], "verticalSwing": [1, 2]}}}
    assert declared(caps) == frozenset({FAN, VERTICAL_SWING})


def test_horizontal_swing_is_declared_only_by_its_own_block():
    """Absence of horizontalSwing means the codeset cannot express it."""
    caps = {"modes": {"4": {"fanSpeeds": [1], "verticalSwing": [1]}}, "keys": [8, 9, 47]}
    assert HORIZONTAL_SWING not in declared(caps)

    caps["modes"]["4"]["horizontalSwing"] = [1, 2]
    assert HORIZONTAL_SWING in declared(caps)


def test_keys_are_a_fallback_for_fan_and_vertical_swing():
    caps = {"keys": [8, 9, 10, 11, 47]}
    assert declared(caps) == frozenset({FAN, VERTICAL_SWING})


def test_a_device_declaring_nothing_gates_nothing():
    """Unknown is not empty; a device with no declaration is exercised on everything."""
    assert declared({}) is None
    assert declared(None) is None
    assert declared({"error": "404"}) is None
    assert declared({"tempRange": [16, 30]}) is None


def test_a_declaration_with_no_controls_is_empty_not_unknown():
    caps = {"modes": {"4": {"tempRanges": [[16, 30]]}}}
    assert declared(caps) == frozenset()


def test_only_codeset_controls_are_gated():
    assert gates("modes.fan_mode") == FAN
    assert gates("modes.horizontalSwingState") == HORIZONTAL_SWING
    assert gates("targetHeat.setpoint") is None
    assert gates("physicalInterface.lockout") is None


BB_V1_CAPS = {
    "version": "1.0",
    "features": {
        "climateControl": {
            "mode": {"userControllable": True, "type": "enum",
                     "validValues": ["off", "heat"]},
            "advancedConfig": {"baseboardHeating": {"controlType": {
                "userControllable": True, "type": "integer",
                "validValues": [0, 4, 5, 6, 7]}}},
        },
        "interface": {
            "wakeOnApproach": {"userControllable": False, "type": "boolean"},
            "lockout": {"userControllable": True, "type": "integer",
                        "validValues": [0, 3]},
            "brightness": {"userControllable": True, "type": "integer"},
        },
    },
}


def test_settings_are_keyed_by_the_state_field_they_govern():
    from pymysa.capabilities import settings

    found = settings(BB_V1_CAPS)
    assert found[("physicalInterface", "lockout")].values == (0, 3)
    assert found[("bbConfig", "controlType")].values == (0, 4, 5, 6, 7)


def test_a_read_only_field_is_declared_as_such():
    from pymysa.capabilities import settings

    assert not settings(BB_V1_CAPS)[("physicalInterface", "wakeOnApproach")].writable


def test_a_field_without_valid_values_is_unconstrained():
    from pymysa.capabilities import settings

    # brightness has no state-field mapping, so nothing is claimed about it.
    assert ("physicalInterface", "brightness") not in settings(BB_V1_CAPS)


def test_a_device_serving_no_document_declares_no_settings():
    from pymysa.capabilities import settings

    assert settings(None) == {}
    assert settings({"error": "404"}) == {}


ALERTS_CAPS = {
    "features": {
        "interface": {
            "lockout": {"userControllable": True, "type": "integer",
                        "validValues": [0, 3]},
            "brightness": {"userControllable": True, "type": "integer"},
        },
        "smart": {
            "smartAlerts": {
                "temperatureAlerts": {
                    "high": {
                        "enabled": {"userControllable": True, "type": "boolean"},
                        "threshold": {"userControllable": True, "type": "float"},
                    }
                }
            },
            "powerMonitoring": {"voltage": {"userControllable": False, "type": "integer"}},
        },
    }
}


def test_a_declared_setting_with_no_state_field_is_reported():
    """Smart alerts are declared writable and appear in no section of the state
    document, so a write to one has nothing to read back."""
    from pymysa.capabilities import undeclared

    paths = dict(undeclared(ALERTS_CAPS))
    assert "smart.smartAlerts.temperatureAlerts.high.enabled" in paths
    assert paths["smart.smartAlerts.temperatureAlerts.high.threshold"] == "float"


def test_a_mapped_setting_is_not_reported_as_undeclared():
    from pymysa.capabilities import undeclared

    assert "interface.lockout" not in dict(undeclared(ALERTS_CAPS))


def test_a_read_only_setting_is_not_reported_as_undeclared():
    """Nothing is missing: it was never writable."""
    from pymysa.capabilities import undeclared

    assert "smart.powerMonitoring.voltage" not in dict(undeclared(ALERTS_CAPS))


def test_a_device_serving_no_document_declares_nothing_undeclared():
    from pymysa.capabilities import undeclared

    assert undeclared(None) == []
    assert undeclared({"error": "404"}) == []
