"""Write every parameter a device supports, confirm it, and put it back.

Each trial is write -> confirm -> restore -> confirm. A final sweep then re-writes
anything not holding its original value, so a trial whose own restore failed still ends
with the device as it was found. Only a parameter the sweep could not put back is
reported as leaving the device changed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..capabilities import declared, gates, settings
from ..confirm import close, in_force
from ..exceptions import MysaError
from ..parameters import (
    CATALOGUE,
    Trial,
    plan,
    reported,
    reported_only,
    untranslated,
)
from ..refusals import classify
from ..transport.rest import MysaRest
from ..writes import Write
from .modes import await_value, restore, retry_under_modes
from .results import (
    NOT_APPLIED,
    NOT_RESTORED,
    PASSED,
    Result,
)


@dataclass
class DeviceReport:
    device_id: str
    name: str
    model: str
    results: list[Result] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.results) and not any(r.failing for r in self.results)

    @property
    def confirmed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def unrestored(self) -> list[Result]:
        return [r for r in self.results if r.status == NOT_RESTORED]


async def exercise_device(
    rest: MysaRest,
    device_id: str,
    name: str,
    model: str,
    settle: float,
    timeout: float,
    announce: Callable[[str], None] = print,
    capabilities: dict[str, Any] | None = None,
) -> DeviceReport:
    report = DeviceReport(device_id, name, model)
    document = _document(await rest.get_state_batch([device_id]), device_id)
    controls = declared(capabilities)
    known = settings(capabilities)
    trials = plan(document, declared=controls, settings=known, model=model)

    if controls is not None:
        gated = {p for p in _reported_names(document) if gates(p) and gates(p) not in controls}
        report.skipped = sorted(f"{p} (not in codeset)" for p in gated)
    report.skipped += [
        f"{note} - no value map" for note in untranslated(document, known, model)
    ]
    report.skipped += [f"{name} (reported only)" for name in reported_only(document)]
    announce(f"\n{name} [{model}] - {len(trials)} parameter(s)")
    for note in report.skipped:
        announce(f"  skipped {note}")

    try:
        for trial in trials:
            result = await _run_trial(rest, device_id, trial, settle, timeout)
            report.results.append(result)
            announce(f"  {result.describe()}")
    finally:
        # Runs whether the trials completed or were interrupted.
        if trials:
            report.results = await _sweep(
                rest, device_id, trials, report.results, settle, timeout, announce
            )

    report.results = await retry_under_modes(
        rest, device_id, trials, report.results, settle, timeout, announce
    )
    return report


async def _sweep(
    rest: MysaRest,
    device_id: str,
    trials: list[Trial],
    results: list[Result],
    settle: float,
    timeout: float,
    announce: Callable[[str], None],
) -> list[Result]:
    """Put anything back that is not holding its original value."""
    batch = await rest.get_state_batch([device_id])
    first: dict[str, Trial] = {}
    for trial in trials:
        first.setdefault(trial.parameter.name, trial)

    stuck: dict[str, Any] = {}
    for name, trial in _restore_order(first):
        parameter = trial.parameter
        current = in_force(batch, device_id, parameter.section, parameter.field)
        if close(current, trial.original):
            continue
        announce(f"  restoring {name} to {trial.original!r}")
        if not await restore(rest, device_id, trial, settle, timeout):
            stuck[name] = current

    repaired: list[Result] = []
    for result in results:
        if result.parameter in stuck:
            repaired.append(
                Result(
                    result.parameter, result.original, result.written, NOT_RESTORED,
                    f"still set to {stuck[result.parameter]!r}",
                )
            )
        elif result.status == NOT_RESTORED:
            # Its own restore failed, the sweep put it back.
            repaired.append(
                Result(result.parameter, result.original, result.written, PASSED)
            )
        else:
            repaired.append(result)
    return repaired


#: Restored before anything else. Every other original was recorded with the device in
#: this state, and a setpoint the current mode does not select is accepted and ignored.
RESTORE_FIRST = ("modes.unitPower", "modes.mode")


def _restore_order(first: dict[str, Trial]) -> list[tuple[str, Trial]]:
    """The order that leaves each restore able to apply.

    Operating state first: these are exercised last precisely because they change how
    everything else behaves, so the sweep has to undo them before it can put the rest
    back. An AC left in dry applies neither setpoint, and both read as unrestorable.

    Then dependent settings before the fields they depend on: switching `wakeOnApproach`
    off first has the device refuse the write that puts `woaSensitivity` back.
    """
    depended = {
        f"{trial.parameter.section}.{trial.parameter.requires[0]}"
        for trial in first.values()
        if trial.parameter.requires is not None
    }

    def key(item: tuple[str, Trial]) -> tuple[int, bool]:
        name = item[0]
        first_rank = (
            RESTORE_FIRST.index(name) if name in RESTORE_FIRST else len(RESTORE_FIRST)
        )
        return (first_rank, name in depended)

    return sorted(first.items(), key=key)


async def _run_trial(
    rest: MysaRest, device_id: str, trial: Trial, settle: float, timeout: float
) -> Result:
    parameter = trial.parameter
    enable = await _requirement(rest, device_id, trial)
    if enable is not None:
        field, required, _ = enable
        await _apply(rest, device_id, parameter.section, field, required, settle, timeout)

    write = Write(parameter.section, {parameter.field: trial.candidate})
    try:
        await rest.update_state(device_id, write.payload())
    except MysaError as err:
        kind, reason = classify(str(err))
        await _disable(rest, device_id, trial, enable, settle, timeout)
        return Result(parameter.name, trial.original, trial.candidate, kind, reason)

    applied = await await_value(
        rest, device_id, parameter.section, parameter.field, trial.candidate, settle, timeout
    )

    if enable is not None:
        # A dependent setting is put back now, not in the sweep: the next trial's
        # original was recorded with its feature off, and the write is refused once it
        # is off again.
        await restore(rest, device_id, trial, settle, timeout)
        await _disable(rest, device_id, trial, enable, settle, timeout)

    if not applied:
        return Result(
            parameter.name, trial.original, trial.candidate, NOT_APPLIED,
            "accepted, device did not take it",
        )
    return Result(parameter.name, trial.original, trial.candidate, PASSED)


async def _apply(
    rest: MysaRest, device_id: str, section: str, field: str, value: Any,
    settle: float, timeout: float,
) -> bool:
    try:
        await rest.update_state(device_id, Write(section, {field: value}).payload())
    except MysaError:
        return False
    return await await_value(rest, device_id, section, field, value, settle, timeout)


async def _requirement(
    rest: MysaRest, device_id: str, trial: Trial
) -> tuple[str, Any, Any] | None:
    """What has to hold for this write, as the device stands now.

    The plan records this from the state the device was found in, but restores are
    deferred to the sweep, so an earlier trial may have left the required field
    somewhere else since.
    """
    requires = trial.parameter.requires
    if requires is None:
        return None
    field, required = requires
    section = trial.parameter.section
    current = in_force(await rest.get_state_batch([device_id]), device_id, section, field)
    if current is None or close(current, required):
        return None
    return (field, required, current)


async def _disable(
    rest: MysaRest, device_id: str, trial: Trial,
    enable: tuple[str, Any, Any] | None, settle: float, timeout: float,
) -> None:
    """Put back a feature that was switched on only to write a setting of it."""
    if enable is None:
        return
    field, _, was = enable
    await _apply(rest, device_id, trial.parameter.section, field, was, settle, timeout)


def _reported_names(document: dict[str, Any]) -> set[str]:
    return {
        p.name
        for p in CATALOGUE
        if p.field in reported(document, p.section)
    }


def _document(batch: dict[str, Any], device_id: str) -> dict[str, Any]:
    entry = batch.get(device_id)
    data = entry.get("data") if isinstance(entry, dict) else None
    return data if isinstance(data, dict) else {}
