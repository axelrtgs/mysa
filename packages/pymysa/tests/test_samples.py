"""Raw captures, and processing them into the publishable tree."""

from __future__ import annotations

import json
from pathlib import Path

from pymysa.debug.samples import READ, WRITE, process, slug, write_raw


def test_raw_captures_are_grouped_by_model_and_operation(tmp_path: Path):
    path = write_raw(tmp_path, "BB-V1-0", READ, "aabbccddeeff", {"a": 1})
    assert path == tmp_path / "BB-V1-0" / "read" / "aabbccddeeff.json"


def test_raw_is_written_verbatim(tmp_path: Path):
    """Raw is local; redacting it would destroy what it is for."""
    payload = {"device": {"Name": "Kitchen", "serial": "SN-1"}, "id": "aabbccddeeff"}
    path = write_raw(tmp_path, "BB-V1-0", READ, "aabbccddeeff", payload)

    assert json.loads(path.read_text()) == payload


def test_process_redacts_into_model_and_operation_directories(tmp_path: Path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    write_raw(raw, "BB-V1-0", READ, "aabbccddeeff", {"deviceId": "aabbccddeeff"})
    write_raw(raw, "BB-V1-0", WRITE, "aabbccddeeff", {"device": "aabbccddeeff"})

    results = process(raw, out)

    assert len(results) == 2
    for item in results:
        assert item.destination.parent.parent.name == "BB-V1-0"
        assert item.destination.parent.name in (READ, WRITE)
        assert "aabbccddeeff" not in item.destination.name
        assert "aabbccddeeff" not in item.destination.read_text()


def test_one_device_keeps_the_same_alias_across_files(tmp_path: Path):
    """Samples stay cross-referenced after redaction."""
    raw, out = tmp_path / "raw", tmp_path / "out"
    write_raw(raw, "BB-V1-0", READ, "aabbccddeeff", {"deviceId": "aabbccddeeff"})
    write_raw(raw, "BB-V1-0", WRITE, "aabbccddeeff", {"device": "aabbccddeeff"})

    names = {item.destination.name for item in process(raw, out)}
    assert len(names) == 1


def test_different_devices_get_different_aliases(tmp_path: Path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    write_raw(raw, "BB-V1-0", READ, "aabbccddeeff", {"deviceId": "aabbccddeeff"})
    write_raw(raw, "BB-V1-0", READ, "ccddeeff0011", {"deviceId": "ccddeeff0011"})

    names = {item.destination.name for item in process(raw, out)}
    assert len(names) == 2


def test_stray_files_outside_the_layout_are_ignored(tmp_path: Path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    (raw / "notes.json").write_text("{}")

    assert process(raw, out) == []


def test_a_model_name_is_made_path_safe():
    assert slug("BB-V1-0") == "BB-V1-0"
    assert slug("../etc") == "---etc"
    assert slug("") == "unknown"
