"""Retrying declined parameters under each mode the device accepted."""

from __future__ import annotations

import contextlib

from pymysa.debug.modes import retry_under_modes
from pymysa.debug.results import NOT_APPLIED, PASSED, Result
from pymysa.parameters import NUMERIC, Parameter, Trial

HEAT = Parameter("targetHeat", "setpoint", NUMERIC, bounds=("lockoutMin", "lockoutMax"))
MODE = Parameter("modes", "mode", "choice", choices=(0, 3, 4))

TRIALS = [Trial(HEAT, 21, 22), Trial(MODE, 3, 4)]


class FakeRest:
    """A device that applies the heat setpoint only while in mode 4."""

    def __init__(self, applies_in=(4,)) -> None:
        self.applies_in = set(applies_in)
        self.state = {
            "targetHeat": {"reported": {"setpoint": 21, "lockoutMin": 5, "lockoutMax": 24}},
            "modes": {"reported": {"mode": 3}},
        }
        self.writes: list[tuple[str, object]] = []

    async def get_state_batch(self, ids):
        return {ids[0]: {"data": self.state}}

    async def update_state(self, device_id, payload):
        section = next(k for k in payload if k != "source")
        field, value = next(iter(payload[section].items()))
        self.writes.append((f"{section}.{field}", value))
        if section == "modes":
            self.state["modes"]["reported"]["mode"] = value
        elif self.state["modes"]["reported"]["mode"] in self.applies_in:
            self.state[section]["reported"][field] = value
        return {"message": "ok"}


async def test_a_declined_parameter_that_applies_in_another_mode_passes():
    rest = FakeRest(applies_in=(4,))
    results = [
        Result("targetHeat.setpoint", 21, 22, NOT_APPLIED, "declined"),
        Result("modes.mode", 3, 4, PASSED),
    ]

    updated = await retry_under_modes(rest, "aaa", TRIALS, results, 0, 0.05, lambda _: None)

    setpoint = next(r for r in updated if r.parameter == "targetHeat.setpoint")
    assert setpoint.status == PASSED
    assert setpoint.applied_in == (4,)


async def test_a_parameter_declined_in_every_mode_stays_not_applied():
    rest = FakeRest(applies_in=())
    results = [
        Result("targetHeat.setpoint", 21, 22, NOT_APPLIED, "declined"),
        Result("modes.mode", 3, 4, PASSED),
    ]

    updated = await retry_under_modes(rest, "aaa", TRIALS, results, 0, 0.05,
                                      lambda _: None, probe_timeout=0.05)

    setpoint = next(r for r in updated if r.parameter == "targetHeat.setpoint")
    assert setpoint.status == NOT_APPLIED
    assert "declined in mode 4" in setpoint.detail


async def test_the_mode_is_put_back_after_retrying():
    rest = FakeRest()
    results = [
        Result("targetHeat.setpoint", 21, 22, NOT_APPLIED, "declined"),
        Result("modes.mode", 3, 4, PASSED),
    ]

    await retry_under_modes(rest, "aaa", TRIALS, results, 0, 0.05, lambda _: None)

    assert rest.state["modes"]["reported"]["mode"] == 3


async def test_nothing_is_retried_when_no_mode_was_accepted():
    rest = FakeRest()
    results = [Result("targetHeat.setpoint", 21, 22, NOT_APPLIED, "declined")]

    updated = await retry_under_modes(rest, "aaa", TRIALS, results, 0, 0.05, lambda _: None)

    assert updated == results
    assert rest.writes == []


async def test_a_clean_run_is_left_alone():
    rest = FakeRest()
    results = [Result("modes.mode", 3, 4, PASSED)]

    updated = await retry_under_modes(rest, "aaa", TRIALS, results, 0, 0.05, lambda _: None)

    assert updated == results


async def test_progress_is_announced_per_mode_and_parameter():
    """The pass is minutes long; one line at the start reads as a hang."""
    rest = FakeRest(applies_in=(4,))
    results = [
        Result("targetHeat.setpoint", 21, 22, NOT_APPLIED, "declined"),
        Result("modes.mode", 3, 4, PASSED),
    ]
    said: list[str] = []

    await retry_under_modes(rest, "aaa", TRIALS, results, 0, 0.05, said.append,
                            probe_timeout=0.05)

    assert any("mode 4:" in line for line in said)
    assert any("applies" in line for line in said)
    assert any("min" in line for line in said)


async def test_a_mode_the_device_will_not_take_is_skipped_not_probed():
    rest = FakeRest(applies_in=())
    rest.state["modes"]["reported"]["mode"] = 3

    class Stubborn(FakeRest):
        async def update_state(self, device_id, payload):
            section = next(k for k in payload if k != "source")
            if section == "modes":
                self.writes.append(("modes.mode", None))
                return {"message": "ok"}      # accepted, never applied
            return await FakeRest.update_state(self, device_id, payload)

    stubborn = Stubborn(applies_in=())
    said: list[str] = []
    results = [
        Result("targetHeat.setpoint", 21, 22, NOT_APPLIED, "declined"),
        Result("modes.mode", 3, 4, PASSED),
    ]

    await retry_under_modes(stubborn, "aaa", TRIALS, results, 0, 0.05, said.append,
                            probe_timeout=0.05)

    assert any("not applied, skipping" in line for line in said)
    # No parameter probes under a mode that never took. Probe lines are the indented
    # ones; the header line legitimately contains the word "declined".
    assert not [line for line in said if line.startswith("      ")]


async def test_the_mode_is_put_back_even_when_a_probe_raises():
    class Exploding(FakeRest):
        async def update_state(self, device_id, payload):
            section = next(k for k in payload if k != "source")
            if section == "targetHeat":
                raise RuntimeError("boom")
            return await FakeRest.update_state(self, device_id, payload)

    rest = Exploding()
    results = [
        Result("targetHeat.setpoint", 21, 22, NOT_APPLIED, "declined"),
        Result("modes.mode", 3, 4, PASSED),
    ]

    with contextlib.suppress(RuntimeError):
        await retry_under_modes(rest, "aaa", TRIALS, results, 0, 0.05, lambda _: None,
                                probe_timeout=0.05)

    assert rest.state["modes"]["reported"]["mode"] == 3
