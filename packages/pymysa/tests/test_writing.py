"""Writing, and what happens between the write and the device taking it."""

from __future__ import annotations

import asyncio

from pymysa.devices import MysaDevice
from pymysa.exceptions import TransportError, UnsupportedCommand, ValueRefused

DOCUMENT = {
    "identity": {"reported": {"model": "BB-V3-0"}},
    "latestTelemetry": {"isConnected": True, "reading": {"roomTemperature": 20.0}},
    "targetHeat": {
        "desired": {"setpoint": 16, "lockoutMin": 5, "lockoutMax": 24},
        "reported": {"setpoint": 16, "lockoutMin": 5, "lockoutMax": 24},
    },
    "modes": {"desired": {"mode": 0}, "reported": {"mode": 0}},
    "physicalInterface": {
        "desired": {"lockout": 0, "activeIntensity": 100, "idleIntensity": 30},
        "reported": {"lockout": 0, "activeIntensity": 100, "idleIntensity": 30},
    },
}

CAPABILITIES = {"features": {
    "climateControl": {"mode": {"userControllable": True, "type": "enum",
                                "validValues": ["off", "heat"]}},
    "interface": {"lockout": {"userControllable": True, "type": "integer",
                              "validValues": [0, 1, 3]}},
}}


class FakeRest:
    """Applies writes to an in-memory document, so a read-back reflects them."""

    def __init__(self, *, apply=True, error=None):
        self.state = {k: {kk: dict(vv) for kk, vv in v.items()} if k != "latestTelemetry"
                      else v for k, v in DOCUMENT.items()}
        self.apply = apply
        self.error = error
        self.writes: list[tuple[str, dict]] = []

    async def update_state(self, device_id, payload):
        section = next(k for k in payload if k != "source")
        self.writes.append((section, dict(payload[section])))
        if self.error is not None:
            raise self.error
        if self.apply:
            self.state[section]["reported"].update(payload[section])
        return {"message": "ok"}

    async def get_state_batch(self, ids):
        return {ids[0]: {"data": self.state}}


def _device(rest, on_write_failed=None):
    device = MysaDevice(
        {"Id": "9070", "Name": "Living Room", "Model": "BB-V3-0"}, rest,
        capabilities=CAPABILITIES, on_write_failed=on_write_failed,
        timeout=0.3, interval=0.02,
    )
    device.update(rest.state)
    return device


async def test_a_write_posts_one_section():
    rest = FakeRest()
    device = _device(rest)

    await device.set_heat_setpoint(21, wait=True)

    assert rest.writes == [("targetHeat", {"setpoint": 21})]


async def test_the_written_value_reads_back_before_the_next_refresh():
    """The caller sees what it set; a UI that waits for a poll shows a stale number."""
    rest = FakeRest(apply=False)
    device = _device(rest)

    await device.set_heat_setpoint(21)

    assert device.heat_setpoint == 21


async def test_a_confirmed_write_settles_to_what_the_device_holds():
    rest = FakeRest()
    device = _device(rest)

    await device.set_heat_setpoint(21, wait=True)

    assert device.heat_setpoint == 21
    assert device._pending == {}


async def test_a_write_the_device_never_takes_is_dropped_and_reported():
    """Accepted with 200 and never applied is common, and is not success (spec 03)."""
    failures: list[tuple[str, object]] = []
    rest = FakeRest(apply=False)
    device = _device(rest, on_write_failed=lambda d, f, v: failures.append((f, v)))

    await device.set_heat_setpoint(21, wait=True)

    assert device.heat_setpoint == 16
    assert failures == [("targetHeat.setpoint", 21)]


async def test_a_schema_refusal_is_the_constraint_it_names():
    rest = FakeRest(error=TransportError(
        '/state/x/update returned 400: {"statusCode":400,"code":"FST_ERR_VALIDATION",'
        '"error":"Bad Request","message":"body/targetHeat/setpoint must be >= 5"}'))
    device = _device(rest)

    try:
        await device.set_heat_setpoint(1)
    except ValueRefused as err:
        assert "must be >= 5" in str(err)
    else:
        raise AssertionError("expected ValueRefused")


async def test_a_capability_refusal_names_the_feature():
    rest = FakeRest(error=TransportError(
        '/state/x/update returned 400: {"error":"Failed to validate request body",'
        '"message":["Wake on approach is not supported"]}'))
    device = _device(rest)

    try:
        await device.set_heat_setpoint(21)
    except UnsupportedCommand as err:
        assert "Wake on approach" in str(err)
    else:
        raise AssertionError("expected UnsupportedCommand")


async def test_an_undeclared_value_is_refused_before_the_request():
    """The backend accepts it with 200 and never applies it, which reads as success."""
    rest = FakeRest()
    device = _device(rest)

    try:
        await device.set_lock("limited")
    except ValueRefused:
        pass
    else:
        raise AssertionError("expected ValueRefused")
    assert rest.writes == []


async def test_a_declared_name_is_written_as_the_value_the_field_holds():
    rest = FakeRest()
    device = _device(rest)

    await device.set_mode("heat", )

    assert rest.writes == [("modes", {"mode": 4})]


async def test_a_field_the_model_does_not_report_cannot_be_written():
    rest = FakeRest()
    device = _device(rest)

    try:
        await device.set_fan_speed("high")
    except UnsupportedCommand:
        pass
    else:
        raise AssertionError("expected UnsupportedCommand")
    assert rest.writes == []


async def test_both_brightnesses_go_in_one_write():
    """The capability document declares them as one setting."""
    rest = FakeRest()
    device = _device(rest)

    await device.set_brightness(active=90, idle=40)

    assert rest.writes == [
        ("physicalInterface", {"activeIntensity": 90, "idleIntensity": 40})
    ]


async def test_confirmation_runs_without_the_caller_waiting():
    rest = FakeRest()
    device = _device(rest)

    await device.set_heat_setpoint(21)
    assert device._pending                      # returned before confirming
    await asyncio.gather(*device._tasks)

    assert device._pending == {}


async def test_closing_cancels_a_confirmation_in_flight():
    rest = FakeRest(apply=False)
    device = _device(rest)

    await device.set_heat_setpoint(21)
    await device.aclose()

    assert device._tasks == set()
