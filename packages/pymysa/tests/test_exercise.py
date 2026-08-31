"""Write, confirm, restore."""

from __future__ import annotations

import contextlib

from pymysa.debug.exercise import exercise_device
from pymysa.debug.results import NOT_APPLIED, NOT_RESTORED, PASSED
from pymysa.exceptions import TransportError
from pymysa.refusals import REJECTED, UNSUPPORTED_KIND

DOCUMENT = {
    "targetHeat": {"reported": {"setpoint": 20, "lockoutMin": 5, "lockoutMax": 24}},
    "physicalInterface": {"reported": {"lockout": 0}},
}


class FakeRest:
    """Applies writes to an in-memory document, so a read-back reflects them."""

    def __init__(self, reject=(), ignore=(), refuse_restore=(), unsupported=()) -> None:
        self.state = {k: {"reported": dict(v["reported"])} for k, v in DOCUMENT.items()}
        self.reject = set(reject)
        self.unsupported = set(unsupported)
        self.ignore = set(ignore)
        self.refuse_restore = set(refuse_restore)
        self.seen: list[str] = []

    async def get_state_batch(self, ids):
        return {ids[0]: {"data": self.state}}

    async def update_state(self, device_id, payload):
        section = next(k for k in payload if k != "source")
        field, value = next(iter(payload[section].items()))
        name = f"{section}.{field}"
        restoring = name in self.seen
        self.seen.append(name)

        if name in self.unsupported:
            raise TransportError(
                '/state/x/update returned 400: {"error":"Failed to validate request '
                'body","message":["Wake on approach is not supported"]}'
            )
        if name in self.reject:
            raise TransportError(
                '/state/x/update returned 400: {"statusCode":400,'
                '"code":"FST_ERR_VALIDATION","error":"Bad Request",'
                '"message":"body/targetHeat/setpoint must be >= 5"}'
            )
        if name in self.ignore:
            return {"message": "ok"}
        if restoring and name in self.refuse_restore:
            return {"message": "ok"}
        self.state[section]["reported"][field] = value
        return {"message": "ok"}


async def _run(rest):
    return await exercise_device(rest, "aaa", "Kitchen", "BB-V1-0", 0, 0.05, lambda _: None)


async def test_a_working_parameter_passes():
    report = await _run(FakeRest())
    assert report.passed
    assert {r.status for r in report.results} == {PASSED}
    assert report.confirmed == len(report.results)


async def test_the_sweep_restores_every_original_value():
    rest = FakeRest()
    await _run(rest)
    assert rest.state["targetHeat"]["reported"]["setpoint"] == 20
    assert rest.state["physicalInterface"]["reported"]["lockout"] == 0


async def test_a_schema_refusal_keeps_the_constraint_and_does_not_fail_the_run():
    """A constraint is a fact about the request, not a defect."""
    report = await _run(FakeRest(reject={"targetHeat.setpoint"}))
    result = next(r for r in report.results if r.parameter == "targetHeat.setpoint")

    assert result.status == REJECTED
    assert result.detail == "body/targetHeat/setpoint must be >= 5"
    assert report.passed


async def test_a_capability_refusal_is_recorded_as_unsupported():
    """The backend naming a feature is a fact about the device."""
    report = await _run(FakeRest(unsupported={"physicalInterface.lockout"}))
    result = next(r for r in report.results if r.parameter == "physicalInterface.lockout")

    assert result.status == UNSUPPORTED_KIND
    assert result.detail == "Wake on approach is not supported"
    assert report.passed


async def test_a_write_the_device_declines_is_not_applied_and_does_not_fail_the_run():
    report = await _run(FakeRest(ignore={"targetHeat.setpoint"}))
    result = next(r for r in report.results if r.parameter == "targetHeat.setpoint")

    assert result.status == NOT_APPLIED
    assert report.passed


async def test_a_device_left_changed_is_reported_separately():
    """An unrestored device needs the operator, not just a failure count."""
    report = await _run(FakeRest(refuse_restore={"targetHeat.setpoint"}))
    result = next(r for r in report.results if r.parameter == "targetHeat.setpoint")

    assert result.status == NOT_RESTORED
    assert report.unrestored == [result]
    assert "still set to" in result.detail
    assert not report.passed


async def test_a_device_with_nothing_writable_yields_no_results():
    class Empty(FakeRest):
        async def get_state_batch(self, ids):
            return {ids[0]: {"data": {"latestTelemetry": {"reading": {"roomTemperature": 21}}}}}

    report = await _run(Empty())
    assert report.results == []
    assert not report.passed


async def test_a_choice_costs_one_write_per_value_plus_one_restore():
    """Restoring after every trial doubled the writes: 3 values cost 6 sets, not 4."""

    class FanRest(FakeRest):
        def __init__(self) -> None:
            super().__init__()
            self.state = {"modes": {"reported": {"fan_mode": 0}}}

    rest = FanRest()
    await exercise_device(rest, "aaa", "AC", "AC-V1-0", 0, 0.05, lambda _: None)

    fan_writes = [name for name in rest.seen if name == "modes.fan_mode"]
    assert len(fan_writes) == 4          # three candidates, one restore
    assert rest.state["modes"]["reported"]["fan_mode"] == 0


async def test_the_sweep_runs_even_when_a_trial_raises():
    """An interrupted run must not leave a device in a written state."""

    class Exploding(FakeRest):
        async def update_state(self, device_id, payload):
            section = next(k for k in payload if k != "source")
            if section == "physicalInterface" and self.state["targetHeat"]["reported"][
                "setpoint"
            ] != 20:
                raise RuntimeError("interrupted")
            return await FakeRest.update_state(self, device_id, payload)

    rest = Exploding()
    with contextlib.suppress(RuntimeError):
        await _run(rest)

    assert rest.state["targetHeat"]["reported"]["setpoint"] == 20


async def test_a_parameter_the_sweep_cannot_restore_is_reported():
    report = await _run(FakeRest(refuse_restore={"targetHeat.setpoint"}))

    assert [r.parameter for r in report.unrestored] == ["targetHeat.setpoint"]
    assert "still set to" in report.unrestored[0].detail


async def test_the_sweep_leaves_a_clean_run_alone():
    rest = FakeRest()
    report = await _run(rest)

    assert report.passed
    assert rest.state["physicalInterface"]["reported"]["lockout"] == 0


async def test_a_dependent_setting_is_written_with_its_feature_enabled():
    """The refusal for a disabled feature reads as though the hardware lacks it."""
    class GatedRest(FakeRest):
        def __init__(self):
            super().__init__()
            self.state["physicalInterface"]["reported"].update(
                {"wakeOnApproach": 0, "woaSensitivity": 50}
            )

        async def update_state(self, device_id, payload):
            section = next(k for k in payload if k != "source")
            field = next(iter(payload[section]))
            body = self.state[section]["reported"]
            if field == "woaSensitivity" and not body.get("wakeOnApproach"):
                raise TransportError(
                    '400: {"error":"Failed to validate request body",'
                    '"message":["Wake on approach is not supported"]}'
                )
            return await FakeRest.update_state(self, device_id, payload)

    rest = GatedRest()
    report = await _run(rest)
    result = next(r for r in report.results if r.parameter == "physicalInterface.woaSensitivity")

    assert result.status == PASSED
    # The feature is switched back off afterwards.
    assert rest.state["physicalInterface"]["reported"]["wakeOnApproach"] == 0
    assert rest.state["physicalInterface"]["reported"]["woaSensitivity"] == 50


async def test_a_requirement_is_met_at_write_time_not_at_plan_time():
    """Restores are deferred, so an earlier trial can undo what a later one needs.

    `intensityMode` is found at 1, which is what `darkRoomLevel` requires, so the plan
    records nothing to switch on. Its own trials then leave it at 3.
    """

    class Adaptive(FakeRest):
        def __init__(self):
            super().__init__()
            self.state["physicalInterface"]["reported"].update(
                {"intensityMode": 1, "darkRoomLevel": 5}
            )

        async def update_state(self, device_id, payload):
            section = next(k for k in payload if k != "source")
            field = next(iter(payload[section]))
            body = self.state[section]["reported"]
            if field == "darkRoomLevel" and body.get("intensityMode") != 1:
                raise TransportError(
                    '400: {"error":"Failed to validate request body",'
                    '"message":["Adaptive brightness is not supported"]}'
                )
            return await FakeRest.update_state(self, device_id, payload)

    rest = Adaptive()
    report = await _run(rest)
    result = next(r for r in report.results if r.parameter == "physicalInterface.darkRoomLevel")

    assert result.status == PASSED
    assert rest.state["physicalInterface"]["reported"]["intensityMode"] == 1
    assert rest.state["physicalInterface"]["reported"]["darkRoomLevel"] == 5


async def test_the_sweep_restores_the_mode_before_what_depends_on_it():
    """An AC left in a mode that selects neither setpoint cannot have one written back."""

    class Moded(FakeRest):
        def __init__(self):
            super().__init__()
            self.state["modes"] = {"reported": {"mode": 4}}

        async def update_state(self, device_id, payload):
            section = next(k for k in payload if k != "source")
            field = next(iter(payload[section]))
            if field == "setpoint" and self.state["modes"]["reported"]["mode"] != 4:
                return {"message": "ok"}          # accepted, never applied
            return await FakeRest.update_state(self, device_id, payload)

    rest = Moded()
    report = await _run(rest)

    assert rest.state["modes"]["reported"]["mode"] == 4
    assert rest.state["targetHeat"]["reported"]["setpoint"] == 20
    assert not report.unrestored
