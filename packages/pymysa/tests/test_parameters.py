"""Building a write plan from a device's own state document."""

from __future__ import annotations

from pymysa.parameters import CATALOGUE, Parameter, candidates, plan

BB_V1 = {
    "targetHeat": {"reported": {"setpoint": 20, "lockoutMin": 5, "lockoutMax": 24}},
    "modes": {"reported": {"mode": 3}},
    "physicalInterface": {"reported": {"lockout": 0, "format": "C", "activeIntensity": 100}},
    "latestTelemetry": {"reading": {"roomTemperature": 23.4}},
}


def test_the_plan_covers_only_fields_the_device_reports():
    names = {trial.parameter.name for trial in plan(BB_V1)}

    assert "targetHeat.setpoint" in names
    assert "physicalInterface.format" in names
    # No AC sections on a baseboard unit, so nothing to exercise there.
    assert "modes.fan_mode" not in names
    assert "targetCool.setpoint" not in names


def test_a_trial_records_the_value_to_restore():
    trial = next(t for t in plan(BB_V1) if t.parameter.name == "targetHeat.setpoint")
    assert trial.original == 20
    assert trial.candidate != 20


def test_a_choice_parameter_yields_one_trial_per_value():
    trials = [t for t in plan(BB_V1) if t.parameter.name == "modes.mode"]
    assert {t.candidate for t in trials} == {0, 1, 4, 7, 8}
    assert all(t.original == 3 for t in trials)


def test_setpoints_stay_inside_the_devices_lockout_range():
    """The backend rejects out-of-range writes, so a plan that ignores bounds
    manufactures failures."""
    at_ceiling = {"targetHeat": {"reported": {"setpoint": 24, "lockoutMin": 5, "lockoutMax": 24}}}
    trial = next(t for t in plan(at_ceiling) if t.parameter.name == "targetHeat.setpoint")
    assert trial.candidate == 23

    at_floor = {"targetHeat": {"reported": {"setpoint": 5, "lockoutMin": 5, "lockoutMax": 24}}}
    trial = next(t for t in plan(at_floor) if t.parameter.name == "targetHeat.setpoint")
    assert trial.candidate == 6


def test_a_toggle_flips():
    parameter = Parameter("physicalInterface", "lockout", "toggle")
    assert candidates(parameter, 0, {}) == [1]
    assert candidates(parameter, 1, {}) == [0]


def test_a_choice_yields_every_other_value():
    parameter = Parameter("modes", "mode", "choice", choices=(0, 1, 2, 3))
    assert candidates(parameter, 3, {}) == [0, 1, 2]


def test_a_device_found_off_is_switched_on():
    """Off to on is only covered if the off state yields the on values."""
    parameter = Parameter("modes", "mode", "choice", choices=(0, 1, 2, 3))
    assert candidates(parameter, 0, {}) == [1, 2, 3]


def test_a_device_found_on_is_switched_off():
    parameter = Parameter("modes", "mode", "choice", choices=(0, 1, 2, 3))
    assert 0 in candidates(parameter, 2, {})


def test_a_single_valued_choice_is_skipped_rather_than_failed():
    parameter = Parameter("modes", "mode", "choice", choices=(3,))
    assert candidates(parameter, 3, {}) == []


def test_a_value_outside_the_declared_set_is_skipped():
    """A device in a state the shape does not describe is not one to guess at."""
    parameter = Parameter("modes", "mode", "choice", choices=(0, 1, 2, 3))
    assert candidates(parameter, 9, {}) == []


def test_percentages_stay_within_zero_and_one_hundred():
    parameter = Parameter("physicalInterface", "activeIntensity", "numeric", step=10)
    assert candidates(parameter, 100, {}) == [90]
    assert candidates(parameter, 0, {}) == [10]


def test_a_field_with_no_room_to_move_is_skipped():
    narrow = {"targetHeat": {"reported": {"setpoint": 5, "lockoutMin": 5, "lockoutMax": 5}}}
    assert not [t for t in plan(narrow) if t.parameter.name == "targetHeat.setpoint"]


def test_a_section_without_a_reported_half_is_still_read():
    flat = {"physicalInterface": {"lockout": 0}}
    assert [t.parameter.name for t in plan(flat)] == ["physicalInterface.lockout"]


def test_every_catalogued_parameter_has_a_way_to_pick_a_value():
    from pymysa.parameters import CHOICE, NESTED_FLAG, NUMERIC, TOGGLE

    for parameter in CATALOGUE:
        assert parameter.kind in (NUMERIC, TOGGLE, CHOICE, NESTED_FLAG)
        if parameter.kind == CHOICE:
            assert len(parameter.choices) >= 2
        if parameter.kind == NESTED_FLAG:
            assert parameter.nested


def test_a_nested_flag_flips_the_key_inside_the_object():
    """cloudFeatures.cloudEarlyOn is {"enabled": false}, not a bare value."""
    from pymysa.parameters import NESTED_FLAG, Parameter, candidates

    parameter = Parameter("cloudFeatures", "cloudEarlyOn", NESTED_FLAG, nested="enabled")
    assert candidates(parameter, {"enabled": False}, {}) == [{"enabled": True}]
    assert candidates(parameter, {"enabled": True}, {}) == [{"enabled": False}]


def test_a_nested_flag_without_its_key_is_skipped():
    from pymysa.parameters import NESTED_FLAG, Parameter, candidates

    parameter = Parameter("cloudFeatures", "cloudEarlyOn", NESTED_FLAG, nested="enabled")
    assert candidates(parameter, {"other": 1}, {}) == []
    assert candidates(parameter, 3, {}) == []


def test_an_unbounded_numeric_is_not_clamped_to_a_percentage():
    """brightRoomLevel is 500; treating it as a percentage would never move it."""
    from pymysa.parameters import NUMERIC, Parameter, candidates

    parameter = Parameter("physicalInterface", "brightRoomLevel", NUMERIC, step=10,
                          unbounded=True)
    assert candidates(parameter, 500, {}) == [510]



def test_a_setting_of_a_disabled_feature_carries_what_to_enable():
    """woaSensitivity is refused while wakeOnApproach is off, as if unsupported."""
    off = {"physicalInterface": {"reported": {"wakeOnApproach": 0, "woaSensitivity": 50}}}
    trial = next(t for t in plan(off) if t.parameter.name == "physicalInterface.woaSensitivity")

    assert trial.enable == ("wakeOnApproach", 1, 0)


def test_nothing_is_enabled_when_the_feature_is_already_on():
    on = {"physicalInterface": {"reported": {"wakeOnApproach": 1, "woaSensitivity": 50}}}
    trial = next(t for t in plan(on) if t.parameter.name == "physicalInterface.woaSensitivity")

    assert trial.enable is None


def test_adaptive_brightness_gates_the_room_level_thresholds():
    off = {"physicalInterface": {"reported": {"intensityMode": 0, "darkRoomLevel": 5}}}
    trial = next(t for t in plan(off) if t.parameter.name == "physicalInterface.darkRoomLevel")

    assert trial.enable == ("intensityMode", 1, 0)


def test_a_parameter_with_no_dependency_never_enables_anything():
    for trial in plan(BB_V1):
        if trial.parameter.requires is None:
            assert trial.enable is None


def test_declared_values_replace_the_hand_written_ones():
    """Writing 1 to lockout was declined because the valid set is [0, 3]."""
    from pymysa.capabilities import Setting
    from pymysa.parameters import candidates

    lockout = next(p for p in CATALOGUE if p.name == "physicalInterface.lockout")
    setting = Setting(writable=True, kind="integer", values=(0, 3))

    assert candidates(lockout, 0, {}, setting) == [3]


def test_a_read_only_field_is_not_exercised():
    from pymysa.capabilities import Setting

    document = {"physicalInterface": {"reported": {"wakeOnApproach": 0, "lockout": 0}}}
    settings = {
        ("physicalInterface", "wakeOnApproach"): Setting(False, "boolean"),
    }
    names = {t.parameter.name for t in plan(document, settings=settings)}

    assert "physicalInterface.wakeOnApproach" not in names
    assert "physicalInterface.lockout" in names


def test_declared_names_are_translated_to_the_values_the_state_field_holds():
    """The document declares mode as off and heat; the field holds 0 and 4."""
    from pymysa.capabilities import Setting
    from pymysa.parameters import candidates

    mode = next(p for p in CATALOGUE if p.name == "modes.mode")
    setting = Setting(writable=True, kind="enum", values=("off", "heat"))

    assert candidates(mode, 0, {}, setting) == [4]


def test_without_a_declaration_the_catalogue_still_applies():
    from pymysa.parameters import candidates

    lockout = next(p for p in CATALOGUE if p.name == "physicalInterface.lockout")
    assert candidates(lockout, 0, {}, None) == [1]


def test_a_large_declared_set_is_sampled_not_enumerated():
    """51 valid setpoints would be 51 trials; bounds and midpoint say the same thing."""
    from pymysa.capabilities import Setting
    from pymysa.parameters import candidates

    setpoint = next(p for p in CATALOGUE if p.name == "targetHeat.setpoint")
    declared = tuple(5 + 0.5 * i for i in range(51))          # 5 .. 30
    setting = Setting(writable=True, kind="float", values=declared)
    body = {"lockoutMin": 5, "lockoutMax": 24}

    chosen = candidates(setpoint, 20, body, setting)

    assert len(chosen) == 3
    assert min(chosen) == 5 and max(chosen) == 24        # clamped to the lockout range
    assert 20 not in chosen


def test_declared_values_outside_the_devices_lockout_are_dropped():
    """The document declares the hardware range; the device narrows it."""
    from pymysa.capabilities import Setting
    from pymysa.parameters import candidates

    setpoint = next(p for p in CATALOGUE if p.name == "targetHeat.setpoint")
    setting = Setting(writable=True, kind="float", values=(5, 20, 28, 30))

    chosen = candidates(setpoint, 21, {"lockoutMin": 5, "lockoutMax": 24}, setting)

    assert chosen == [5, 20]


def test_a_small_declared_set_is_used_whole():
    from pymysa.capabilities import Setting
    from pymysa.parameters import candidates

    control = next(p for p in CATALOGUE if p.name == "bbConfig.controlType")
    setting = Setting(writable=True, kind="integer", values=(0, 4, 5, 6, 7))

    assert candidates(control, 7, {}, setting) == [0, 4, 5, 6]


def test_a_declared_name_no_map_translates_is_not_written():
    """`sensing.temperature.trackingSensor` declares "internal"; the field holds 0.

    Writing the name back is refused by the schema, which reads as a broken write path
    rather than a meaning nobody has established yet.
    """
    from pymysa.capabilities import Setting
    from pymysa.parameters import candidates

    tracking = next(p for p in CATALOGUE if p.name == "tracking.tracking")
    setting = Setting(writable=True, kind="enum", values=("internal", "remote"))

    assert candidates(tracking, 0, {}, setting) == []


def test_untranslated_declarations_are_reported():
    from pymysa.capabilities import Setting
    from pymysa.parameters import untranslated

    document = {"tracking": {"reported": {"tracking": 0, "ambientOffset": 0}}}
    known = {
        ("tracking", "tracking"): Setting(True, "enum", ("internal", "remote")),
        ("tracking", "ambientOffset"): Setting(True, "float", (-5, 0, 5)),
    }

    reported = untranslated(document, known)

    assert len(reported) == 1
    assert reported[0].startswith("tracking.tracking")
    assert "internal" in reported[0]


REPORTED_ONLY = {
    "modes": {
        "desired": {"mode": 3, "fan_mode": 0},
        "reported": {"mode": 3, "fan_mode": 0, "unitPower": 2},
    },
}


def test_a_field_with_no_desired_half_is_not_written():
    """An AC-V1 reports `modes.unitPower` and the backend holds no desired value.

    The write is accepted and dropped, in every mode, which reads as a device declining
    it rather than a field that was never writable.
    """
    names = {trial.parameter.name for trial in plan(REPORTED_ONLY)}

    assert "modes.fan_mode" in names
    assert "modes.unitPower" not in names


def test_reported_only_fields_are_listed():
    from pymysa.parameters import reported_only

    assert reported_only(REPORTED_ONLY) == ["modes.unitPower"]


def test_a_section_with_no_shadow_pair_is_still_planned():
    """A flat section carries no desired half, and that says nothing about writing it."""
    flat = {"cloudFeatures": {"cloudEarlyOn": {"enabled": True}}}

    assert {t.parameter.name for t in plan(flat)} == {"cloudFeatures.cloudEarlyOn"}
