"""Constants that the protocol depends on."""

from __future__ import annotations

from pymysa import const


def test_the_two_rest_hosts_are_distinct():
    """Firmware lives on the legacy host; everything else on the backend."""
    assert const.API_BASE_URL == "https://mysa-backend.mysa.cloud"
    assert const.LEGACY_BASE_URL == "https://app-prod.mysa.cloud"


def test_cognito_endpoint_matches_the_region():
    assert const.AWS_REGION in const.COGNITO_IDP_URL
    assert const.COGNITO_IDP_URL.startswith("https://cognito-idp.")


def test_amz_framing_is_the_json_11_protocol():
    assert const.AMZ_JSON == "application/x-amz-json-1.1"
    assert const.INITIATE_AUTH_TARGET.endswith(".InitiateAuth")


def test_no_mqtt_constants_remain():
    for removed in (
        "MQTT_ENDPOINT", "TOPIC_IN", "TOPIC_OUT", "MessageType",
        "AC_STATE_KEYS", "STATUS_STREAM_TIMEOUT", "FULL_COVERAGE",
        "COGNITO_IDENTITY_POOL_ID",
    ):
        assert not hasattr(const, removed), removed
