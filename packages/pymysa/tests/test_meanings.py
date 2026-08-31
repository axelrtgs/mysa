"""Value-to-name maps, and what counts as unmapped."""

from __future__ import annotations

from pymysa.meanings import is_mapped_field, name_of, unmapped


def test_established_values_have_names():
    assert name_of("modes", "mode", 0) == "off"
    assert name_of("modes", "mode", 4) == "heat"
    assert name_of("physicalInterface", "format", "F") == "fahrenheit"


def test_a_value_nobody_has_watched_change_has_no_name():
    assert name_of("modes", "mode", 5) is None


def test_a_field_whose_values_are_not_names_is_not_mapped():
    """A setpoint is a number, not a name; it is never 'unmapped'."""
    assert not is_mapped_field("targetHeat", "setpoint")
    assert is_mapped_field("modes", "mode")


def test_unmapped_lists_only_values_of_mapped_fields():
    body = {"mode": 5, "fan_mode": 2, "timestamp": 1}
    assert unmapped("modes", body) == [("mode", 5)]


def test_a_fully_mapped_section_reports_nothing():
    assert unmapped("modes", {"mode": 4}) == []


def test_a_meaning_can_be_per_model():
    """controlType takes 0,4,5,6,7 on a BB-V1 and 0,1,2 on a BB-V3; 4 is radiant on one
    and not a value at all on the other."""
    assert name_of("bbConfig", "controlType", 4, "BB-V1-0") == "radiant"
    assert name_of("bbConfig", "controlType", 4, "BB-V3-0") is None


def test_a_model_without_its_own_map_falls_back_to_the_shared_one():
    assert name_of("modes", "mode", 0, "BB-V3-0") == "off"
    assert name_of("modes", "mode", 0) == "off"


def test_the_heater_types_observed_on_a_bb_v1_are_all_named():
    for value in (0, 4, 5, 6, 7):
        assert name_of("bbConfig", "controlType", value, "BB-V1-0")


def test_lockout_names_match_what_the_app_does():
    assert name_of("physicalInterface", "lockout", 0) == "unlocked"
    assert name_of("physicalInterface", "lockout", 3) == "full"


def test_unmapped_respects_the_model():
    body = {"controlType": 4}
    assert unmapped("bbConfig", body, "BB-V1-0") == []
    assert unmapped("bbConfig", body, "BB-V3-0") == [("controlType", 4)]


def test_a_declared_name_resolves_to_the_models_own_value():
    """The same name is a different value on each model."""
    from pymysa.meanings import value_for

    assert value_for("bbConfig", "controlType", "radiant", "BB-V1-0") == 4
    assert value_for("bbConfig", "controlType", "radiant", "BB-V3-0") == 2


def test_an_unmapped_name_passes_through_unchanged():
    from pymysa.meanings import value_for

    assert value_for("bbConfig", "controlType", "hydronic", "BB-V1-0") == "hydronic"


def test_a_setpoint_is_never_unmapped():
    """Its values are numbers, not names."""
    assert unmapped("targetHeat", {"setpoint": 21}) == []


def test_lockout_has_a_third_state_on_a_v3():
    """Not a boolean: limited restricts the setpoint to the lockout range."""
    assert name_of("physicalInterface", "lockout", 1, "BB-V3-0") == (
        "limited to the lockout range"
    )
    assert name_of("physicalInterface", "lockout", 3, "BB-V3-0") == "full"
    # A BB-V1 declares only 0 and 3, so 1 has no meaning there.
    assert name_of("physicalInterface", "lockout", 1, "BB-V1-0") is None


def test_adaptive_brightness_has_both_states_named():
    assert name_of("physicalInterface", "intensityMode", 0) == "fixed"
    assert name_of("physicalInterface", "intensityMode", 1) == "adaptive"


def test_a_value_that_is_not_a_scalar_does_not_crash_the_lookup():
    """cloudFeatures.cloudEarlyOn holds {"enabled": bool}, which is not a dict key."""
    assert name_of("cloudFeatures", "cloudEarlyOn", {"enabled": True}) is None
    assert name_of("modes", "mode", ["a", "list"]) is None


def test_unmapped_survives_a_structured_value():
    assert unmapped("cloudFeatures", {"cloudEarlyOn": {"enabled": True}}) == []


def test_the_two_baseboard_models_name_control_type_differently():
    """1 is fan forced on a V3 and not a valid value on a V1."""
    assert name_of("bbConfig", "controlType", 1, "BB-V3-0") == "fan forced"
    assert name_of("bbConfig", "controlType", 2, "BB-V3-0") == "radiant"
    assert name_of("bbConfig", "controlType", 1, "BB-V1-0") is None
    assert name_of("bbConfig", "controlType", 4, "BB-V3-0") is None


def test_baseboard_is_zero_on_both_models():
    for model in ("BB-V1-0", "BB-V3-0"):
        assert name_of("bbConfig", "controlType", 0, model) == "baseboard"
