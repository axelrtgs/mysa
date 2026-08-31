"""Classifying a refused write."""

from __future__ import annotations

from pymysa.refusals import ERROR, REJECTED, UNSUPPORTED_KIND, classify

SCHEMA = (
    '/state/x/update returned 400: {"statusCode":400,"code":"FST_ERR_VALIDATION",'
    '"error":"Bad Request","message":"body/targetHeat/setpoint must be >= 5"}'
)
CONST = (
    '/state/x/update returned 400: {"statusCode":400,"code":"FST_ERR_VALIDATION",'
    '"error":"Bad Request","message":"body/modes/mode must be equal to constant"}'
)
CAPABILITY = (
    '/state/x/update returned 400: {"error":"Failed to validate request body",'
    '"message":["Wake on approach is not supported"]}'
)


def test_a_schema_refusal_keeps_the_constraint():
    kind, reason = classify(SCHEMA)
    assert kind == REJECTED
    assert reason == "body/targetHeat/setpoint must be >= 5"


def test_a_const_refusal_is_still_a_schema_refusal():
    kind, reason = classify(CONST)
    assert kind == REJECTED
    assert "must be equal to constant" in reason


def test_a_capability_refusal_is_distinguished_from_a_schema_one():
    """One describes the request, the other describes the device."""
    kind, reason = classify(CAPABILITY)
    assert kind == UNSUPPORTED_KIND
    assert reason == "Wake on approach is not supported"


def test_a_message_list_is_joined():
    kind, reason = classify(
        '400: {"error":"x","message":["Wake on approach is not supported","and more"]}'
    )
    assert kind == UNSUPPORTED_KIND
    assert reason == "Wake on approach is not supported; and more"


def test_anything_unclassifiable_is_an_error():
    kind, reason = classify("connection reset by peer")
    assert kind == ERROR
    assert reason == "connection reset by peer"


def test_a_non_json_body_falls_back_to_the_whole_message():
    kind, reason = classify("502 Bad Gateway")
    assert kind == ERROR
    assert reason == "502 Bad Gateway"
