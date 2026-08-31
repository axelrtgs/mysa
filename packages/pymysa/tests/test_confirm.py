"""Read-after-write confirmation: does a read return what was written."""

from __future__ import annotations

from pymysa.confirm import Confirmation, close, in_force, sections, telemetry_value

BATCH = {
    "aaa": {
        "data": {
            "targetHeat": {
                "desired": {"setpoint": 21},
                "reported": {"setpoint": 21},
            },
            "latestTelemetry": {"reading": {"heatSetpoint": 20, "mode": 3}},
            "drState": {"inEvent": False},
            "schedule": {"holding": True, "resolved": True},
            "cloudFeatures": {"cloudEarlyOn": {"enabled": False}},
        }
    }
}


def test_every_section_is_returned_shadow_pair_or_not():
    found = sections(BATCH, "aaa")
    assert {"targetHeat", "drState", "schedule", "cloudFeatures"} <= set(found)


def test_a_flat_section_is_its_own_value_in_force():
    """schedule and cloudFeatures have no reported half; the section is the value."""
    assert in_force(BATCH, "aaa", "schedule", "holding") is True
    assert in_force(BATCH, "aaa", "cloudFeatures", "cloudEarlyOn") == {"enabled": False}


def test_a_shadow_pair_still_reads_from_reported():
    assert in_force(BATCH, "aaa", "targetHeat", "setpoint") == 21


def test_shadow_distinguishes_the_two_shapes():
    from pymysa.confirm import shadow

    assert shadow(BATCH, "aaa", "targetHeat") is not None
    assert shadow(BATCH, "aaa", "schedule") is None


def test_the_value_in_force_comes_from_reported():
    assert in_force(BATCH, "aaa", "targetHeat", "setpoint") == 21


def test_an_absent_section_reads_as_nothing():
    assert in_force(BATCH, "aaa", "targetCool", "setpoint") is None
    assert in_force(BATCH, "zzz", "targetHeat", "setpoint") is None


def test_telemetry_gives_the_devices_own_copy_where_one_is_mapped():
    assert telemetry_value(BATCH, "aaa", "targetHeat", "setpoint") == 20
    assert telemetry_value(BATCH, "aaa", "modes", "mode") == 3


def test_fields_without_a_telemetry_mirror_return_nothing():
    assert telemetry_value(BATCH, "aaa", "physicalInterface", "lockout") is None


def test_numbers_compare_with_tolerance_since_the_cloud_may_round():
    assert close(20, 20.0)
    assert close(20.02, 20.0)
    assert not close(20.5, 20.0)


def test_strings_compare_exactly():
    assert close("F", "F")
    assert not close("C", "F")


def test_a_matching_read_back_is_confirmation():
    result = Confirmation("targetHeat", "setpoint", 21, after=0.6, observed=21)
    assert result.confirmed
    assert "confirmed after 0.6s" in result.describe()


def test_an_unconfirmed_write_reports_what_came_back_instead():
    result = Confirmation("targetHeat", "setpoint", 2, observed=20)
    assert not result.confirmed
    assert "read back 20" in result.describe()


def test_lagging_device_telemetry_is_noted_without_failing_the_write():
    """The shadow is the value in force; telemetry catches up on its own cadence."""
    result = Confirmation("targetHeat", "setpoint", 21, after=0.6, observed=21, telemetry=20)
    assert result.confirmed
    assert "telemetry still reports 20" in result.describe()


def test_agreeing_telemetry_adds_nothing_to_the_message():
    result = Confirmation("targetHeat", "setpoint", 21, after=0.6, observed=21, telemetry=21)
    assert "telemetry" not in result.describe()
