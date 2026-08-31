"""Redaction must remove identifiers without destroying message correlation."""

from __future__ import annotations

import json

from pymysa.debug.redact import Redactor


def test_denied_keys_are_removed() -> None:
    r = Redactor()
    out = r.scrub(
        {
            "Owner": "someone@example.com",
            "AllowedUsers": ["a", "b"],
            "Home": "home-123",
            "serial_number": "SN12345",
            "pubKeyHash": "abc",
            "Model": "BB-V1-0",
        }
    )
    assert out["Owner"] == "<redacted>"
    assert out["AllowedUsers"] == "<redacted>"
    assert out["Home"] == "<redacted>"
    assert out["serial_number"] == "<redacted>"
    assert out["pubKeyHash"] == "<redacted>"
    assert out["Model"] == "BB-V1-0", "protocol fields must survive"


def test_device_ids_alias_consistently() -> None:
    r = Redactor()
    alias = r.device_alias("aabbccddeeff")
    out = r.scrub(
        {
            "deviceId": "aabbccddeeff",
            "messages": [{"topic": "/v1/dev/aabbccddeeff/out"}],
            "other": {"Device": "aabbccddeeff"},
        }
    )
    assert out["deviceId"] == alias
    assert out["other"]["Device"] == alias
    assert alias.startswith("device-")


def test_token_shaped_values_are_removed_regardless_of_key() -> None:
    r = Redactor()
    out = r.scrub({"harmless": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"})
    assert out["harmless"] == "<redacted>"


def test_long_unmatched_strings_are_flagged_for_review() -> None:
    r = Redactor()
    r.scrub({"faultTest": "x" * 200})
    assert any("faultTest" in path for path in r.review)


def test_numbers_and_structure_are_preserved() -> None:
    r = Redactor()
    payload = {"SupportedCaps": {"keys": [1, 47], "tempRange": [16, 30]}}
    assert r.scrub(payload) == payload


def test_device_ids_are_rewritten_inside_strings() -> None:
    """Topics embed the device id; exact-value matching alone leaks it."""
    r = Redactor()
    out = r.scrub({"topic": "/v1/dev/aabbccddeeff/out", "deviceId": "aabbccddeeff"})
    assert "aabbccddeeff" not in out["topic"]
    assert out["topic"] == f"/v1/dev/{out['deviceId']}/out"


def test_identifier_discovered_after_use_is_still_rewritten() -> None:
    """Two passes: the topic precedes the deviceId key in traversal order."""
    r = Redactor()
    out = r.scrub({"a_topic": "/v1/dev/bbccddeeff00/out", "z_deviceId": "bbccddeeff00"})
    assert "bbccddeeff00" not in out["a_topic"]


def test_no_device_id_survives_anywhere_in_a_bundle() -> None:
    r = Redactor()
    bundle = {
        "device": {"record": {"Device": "ddeeff001122"}},
        "steps": [{"messages": [{"topic": "/v1/dev/ddeeff001122/out",
                                 "payload": {"deviceId": "ddeeff001122"}}]}],
    }
    import json
    assert "ddeeff001122" not in json.dumps(r.scrub(bundle))


def test_device_ids_in_dict_keys_are_rewritten() -> None:
    """/state/batch is keyed by device id, which the value-only pass walked straight past."""
    redactor = Redactor()
    scrubbed = redactor.scrub({"state_batch": {"ccddeeff0011": {"mode": 0}}})

    (alias,) = scrubbed["state_batch"]
    assert alias != "ccddeeff0011"
    assert "ccddeeff0011" not in json.dumps(scrubbed)


def test_a_key_and_a_value_holding_the_same_id_get_the_same_alias() -> None:
    redactor = Redactor()
    scrubbed = redactor.scrub(
        {"ccddeeff0011": {"deviceId": "ccddeeff0011"}}
    )

    (alias,) = scrubbed
    assert scrubbed[alias]["deviceId"] == alias


LOCATION_KEYS = [
    "postalCode", "postal_code", "zip", "zipCode", "address", "streetAddress",
    "macAddress", "latitude", "longitude", "city", "province", "country", "lat", "lng",
]

#: Feature flags whose names read like something sensitive and are not.
CLOUD_FEATURE_KEYS = ["geofence", "scheduling", "zoning", "earlyOn", "cloudEarlyOn"]

#: Real field names from the captured samples. None of these may be redacted.
PROTOCOL_KEYS = [
    "capacity", "state", "drState", "SwingState", "inEvent", "isConnected",
    "lockoutModes", "dutyCycle", "controlType", "intensityMode", "roomTemperature",
    "brightRoomLevel", "darkRoomLevel", "verticalSwingState", "horizontalSwingState",
    "fan_mode", "hysteresisBandLow", "trackingFallback", "remoteTTL", "codesetVersion",
    "commissioningWindowOpen", "resolved", "holding", "cloudEarlyOn", "wattage",
    "coolSetpoint", "effectiveSetpoint", "thermostaticOffset", "vaSteadyStateTemp",
]


def test_location_identifies_a_home_and_is_redacted():
    redactor = Redactor()
    scrubbed = redactor.scrub({key: "value" for key in LOCATION_KEYS})

    assert set(scrubbed.values()) == {"<redacted>"}


def test_no_protocol_field_is_caught_by_a_location_pattern():
    """`city` matches `capacity` and `state` matches `drState` unless anchored."""
    redactor = Redactor()
    scrubbed = redactor.scrub({key: 1 for key in PROTOCOL_KEYS})

    kept = {key for key, value in scrubbed.items() if value != "<redacted>"}
    assert kept == set(PROTOCOL_KEYS)


def test_a_feature_flag_is_not_a_location():
    """`geofence` sits with scheduling and zoning and holds a boolean, not a place."""
    redactor = Redactor()
    scrubbed = redactor.scrub({key: True for key in CLOUD_FEATURE_KEYS})

    assert all(scrubbed[key] is True for key in CLOUD_FEATURE_KEYS)


def test_a_home_record_keeps_its_shape_without_its_location():
    redactor = Redactor()
    scrubbed = redactor.scrub(
        {"Homes": [{"Id": "h-1", "Name": "House", "postalCode": "A1A 1A1",
                    "timezone": "America/Toronto"}]}
    )

    home = scrubbed["Homes"][0]
    assert home["postalCode"] == "<redacted>"
    assert home["timezone"] == "America/Toronto"
