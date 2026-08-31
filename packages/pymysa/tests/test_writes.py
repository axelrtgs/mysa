"""Write payload shape."""

from __future__ import annotations

from pymysa.writes import SOURCE_APP, Write


def test_a_write_carries_one_section_and_the_source_tag():
    assert Write("targetHeat", {"setpoint": 21}).payload() == {
        "source": SOURCE_APP,
        "targetHeat": {"setpoint": 21},
    }


def test_several_fields_in_one_section_go_in_one_payload():
    payload = Write("targetHeat", {"lockoutMin": 5, "lockoutMax": 24}).payload()
    assert payload["targetHeat"] == {"lockoutMin": 5, "lockoutMax": 24}


def test_the_payload_does_not_alias_the_write():
    """A caller mutating the payload must not change the record of what was sent."""
    write = Write("modes", {"mode": 3})
    write.payload()["modes"]["mode"] = 99
    assert write.fields == {"mode": 3}
