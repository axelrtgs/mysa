"""Choosing one device per distinct configuration."""

from __future__ import annotations

from pymysa.debug.coverage import configuration, representatives


def _device(model: str) -> dict:
    return {"Model": model, "Name": model}


def _document(model: str, fw: str, *sections: str) -> dict:
    document = {"identity": {"reported": {"model": model, "fw": fw}}}
    for section in sections:
        document[section] = {"reported": {}}
    return document


def test_identical_units_collapse_to_one():
    devices = {"b": _device("BB-V1-0"), "a": _device("BB-V1-0")}
    documents = {
        "a": _document("BB-V1-0", "3.17.3.1", "modes"),
        "b": _document("BB-V1-0", "3.17.3.1", "modes"),
    }

    assert representatives(devices, documents) == {"a": ["b"]}


def test_the_lowest_id_represents_its_group():
    """Repeated runs cover the same unit, so its samples share one baseline."""
    devices = {"z": _device("BB-V1-0"), "a": _device("BB-V1-0")}
    documents = {
        "a": _document("BB-V1-0", "3.17.3.1", "modes"),
        "z": _document("BB-V1-0", "3.17.3.1", "modes"),
    }

    assert list(representatives(devices, documents)) == ["a"]


def test_different_firmware_is_a_different_configuration():
    devices = {"a": _device("BB-V1-0"), "b": _device("BB-V1-0")}
    documents = {
        "a": _document("BB-V1-0", "3.17.3.1", "modes"),
        "b": _document("BB-V1-0", "5.1.9", "modes"),
    }

    assert representatives(devices, documents) == {"a": [], "b": []}


def test_units_differing_only_in_sections_are_both_exercised():
    """Two AC-V1-0 on one firmware differ in acConfig; collapsing them hides it."""
    devices = {"a": _device("AC-V1-0"), "b": _device("AC-V1-0")}
    documents = {
        "a": _document("AC-V1-0", "3.17.5.9", "modes", "acConfig"),
        "b": _document("AC-V1-0", "3.17.5.9", "modes"),
    }

    assert representatives(devices, documents) == {"a": [], "b": []}


def test_a_model_falls_back_to_the_device_record():
    config = configuration({"Model": "BB-V2-0"}, {})
    assert config.model == "BB-V2-0"
    assert config.firmware == "?"


def test_identity_wins_over_the_device_record():
    config = configuration(
        {"Model": "stale"}, {"identity": {"reported": {"model": "BB-V3-0", "fw": "5.1.9"}}}
    )
    assert (config.model, config.firmware) == ("BB-V3-0", "5.1.9")
