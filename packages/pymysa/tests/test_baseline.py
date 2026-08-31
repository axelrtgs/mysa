"""Comparing a capture against the committed sample for its model."""

from __future__ import annotations

import json
from pathlib import Path

from pymysa.debug.baseline import ERROR, INFO, WARNING, compare, failed, load

SEMANTICS = {
    ("targetHeat", "setpoint"): "target_temperature",
    ("physicalInterface", "lockout"): "lock",
    ("latestTelemetry.reading", "roomTemperature"): "current_temperature",
}

BASELINE = {
    "targetHeat": frozenset({"setpoint", "lockoutMin"}),
    "physicalInterface": frozenset({"lockout"}),
    "bbConfig": frozenset({"pidFastKd"}),
}


def _observed(**sections: list[str]) -> dict[str, list[str]]:
    return dict(sections)


def test_a_missing_critical_field_is_an_error():
    differences = compare(
        "BB-V1-0",
        _observed(targetHeat=["lockoutMin"], physicalInterface=["lockout"],
                  bbConfig=["pidFastKd"]),
        BASELINE,
        SEMANTICS,
    )
    (item,) = [d for d in differences if d.field == "setpoint"]

    assert item.kind == "missing"
    assert item.severity == ERROR
    assert item.semantic == "target_temperature"
    assert failed(differences)


def test_a_missing_control_is_a_warning_and_does_not_fail_the_run():
    differences = compare(
        "BB-V1-0",
        _observed(targetHeat=["setpoint", "lockoutMin"], physicalInterface=[],
                  bbConfig=["pidFastKd"]),
        BASELINE,
        SEMANTICS,
    )
    (item,) = [d for d in differences if d.field == "lockout"]

    assert item.severity == WARNING
    assert not failed(differences)


def test_a_missing_field_nobody_reads_is_informational():
    differences = compare(
        "BB-V1-0",
        _observed(targetHeat=["setpoint", "lockoutMin"], physicalInterface=["lockout"],
                  bbConfig=[]),
        BASELINE,
        SEMANTICS,
    )
    (item,) = [d for d in differences if d.field == "pidFastKd"]

    assert item.severity == INFO
    assert item.semantic is None
    assert not failed(differences)


def test_an_added_field_is_reported_as_new():
    differences = compare(
        "BB-V1-0",
        _observed(targetHeat=["setpoint", "lockoutMin", "lockoutMax"],
                  physicalInterface=["lockout"], bbConfig=["pidFastKd"]),
        BASELINE,
        SEMANTICS,
    )
    (item,) = [d for d in differences if d.kind == "new"]

    assert item.field == "lockoutMax"
    assert item.severity == INFO
    assert not failed(differences)


def test_a_whole_section_gone_reports_each_field():
    differences = compare("BB-V1-0", _observed(), BASELINE, SEMANTICS)
    assert {d.field for d in differences} == {"setpoint", "lockoutMin", "lockout", "pidFastKd"}


def test_a_model_with_no_baseline_reports_nothing():
    """Everything is new and nothing is missing until a sample is committed."""
    assert compare("XX-V9-0", _observed(targetHeat=["setpoint"]), {}, SEMANTICS) == []


def _samples(tmp_path: Path) -> Path:
    directory = tmp_path / "AC-V1-0" / "read"
    directory.mkdir(parents=True)
    (directory / "device-a.json").write_text(
        json.dumps({"sections": {"modes": ["mode"], "acConfig": ["codesetVersion"]}})
    )
    (directory / "device-b.json").write_text(
        json.dumps({"sections": {"modes": ["mode"]}})
    )
    return tmp_path


def test_a_baseline_is_the_units_own_sample_not_the_models(tmp_path: Path):
    """Two units of one model differ; a unioned baseline invents missing fields."""
    root = _samples(tmp_path)

    assert load(root, "AC-V1-0", "device-b") == {"modes": frozenset({"mode"})}
    assert "acConfig" in load(root, "AC-V1-0", "device-a")


def test_a_unit_missing_a_peers_section_reports_no_missing_field(tmp_path: Path):
    root = _samples(tmp_path)
    observed = {"modes": ["mode"]}

    assert compare("AC-V1-0", observed, load(root, "AC-V1-0", "device-b"), SEMANTICS) == []


def test_variation_between_units_is_reported_from_one_side_only(tmp_path: Path):
    """A unit having a field and its peer lacking it is one fact, not two."""
    from pymysa.debug.baseline import compare_peers, peers

    root = _samples(tmp_path)

    # The unit that carries acConfig reports the variation.
    carrier = compare_peers(
        "AC-V1-0", {"modes": ["mode"], "acConfig": ["codesetVersion"]},
        peers(root, "AC-V1-0", "device-a"),
    )
    assert [(d.field, d.kind) for d in carrier] == [
        ("codesetVersion", "varies between units")
    ]

    # The unit that lacks it stays quiet.
    assert compare_peers(
        "AC-V1-0", {"modes": ["mode"]}, peers(root, "AC-V1-0", "device-b")
    ) == []


def test_a_field_already_reported_against_its_own_baseline_is_not_repeated(tmp_path: Path):
    from pymysa.debug.baseline import compare_peers, peers

    root = _samples(tmp_path)
    observed = {"modes": ["mode"], "acConfig": ["codesetVersion"]}
    other = peers(root, "AC-V1-0", "device-a")

    assert compare_peers("AC-V1-0", observed, other,
                         frozenset({("acConfig", "codesetVersion")})) == []


def test_peers_excludes_the_unit_itself(tmp_path: Path):
    from pymysa.debug.baseline import peers

    root = _samples(tmp_path)
    assert "acConfig" not in peers(root, "AC-V1-0", "device-a")


def test_load_returns_nothing_for_a_unit_with_no_sample(tmp_path: Path):
    assert load(tmp_path, "XX-V9-0", "device-z") == {}


def test_a_value_outside_its_enum_is_reported_with_the_expectation():
    from pymysa.debug.baseline import check_values

    document = {"modes": {"reported": {"mode": 9}}}
    (item,) = check_values("AC-V1-0", document, SEMANTICS)

    assert item.kind == "unexpected"
    assert "= 9 (expected one of 0, 1, 3, 4, 7, 8)" in item.detail
    assert item.severity == INFO  # no device class maps modes.mode yet


def test_an_out_of_shape_critical_field_is_an_error():
    from pymysa.debug.baseline import check_values, failed

    document = {"targetHeat": {"reported": {"setpoint": 30, "lockoutMin": 5, "lockoutMax": 24}}}
    (item,) = check_values("BB-V1-0", document, SEMANTICS)

    assert item.severity == ERROR
    assert "expected 5-24" in item.detail
    assert failed([item])


def test_values_inside_their_shape_are_not_reported():
    from pymysa.debug.baseline import check_values

    document = {"targetHeat": {"reported": {"setpoint": 21, "lockoutMin": 5, "lockoutMax": 24}}}
    assert check_values("BB-V1-0", document, SEMANTICS) == []


def test_nested_telemetry_readings_are_checked():
    from pymysa.debug.baseline import check_values

    document = {"latestTelemetry": {"isConnected": True, "reading": {"humidity": 140}}}
    (item,) = check_values("BB-V1-0", document, SEMANTICS)

    assert item.section == "latestTelemetry.reading"
    assert item.field == "humidity"


def test_unshaped_fields_are_never_reported():
    from pymysa.debug.baseline import check_values

    document = {"identity": {"reported": {"fw": "5.1.9", "model": "BB-V3-0"}}}
    assert check_values("BB-V3-0", document, SEMANTICS) == []


def test_a_missing_critical_field_is_an_error_now_that_device_classes_map_it():
    """Severity is what a device class reads the field as (spec 07)."""
    from pymysa.devices import semantics

    names = semantics("BB-V3-0")
    baseline = {"targetHeat": frozenset({"setpoint", "lockoutMin", "lockoutMax"})}
    observed = {"targetHeat": ["lockoutMin", "lockoutMax"]}

    differences = compare("BB-V3-0", observed, baseline, names)

    assert [(d.field, d.severity) for d in differences] == [("setpoint", ERROR)]
