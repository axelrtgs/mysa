"""Re-attempting what a device declined, under each mode it accepted.

A write accepted and not applied is usually a parameter the device's current mode does
not select: an AC in cool applies the cool setpoint and ignores the heat setpoint. Which
modes select a parameter is a fact about the device, and this establishes it rather than
assuming it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from ..confirm import close, in_force
from ..exceptions import MysaError
from ..parameters import Trial
from ..transport.rest import MysaRest
from ..writes import Write
from .results import NOT_APPLIED, PASSED, Result

#: A device confirms a write it accepts within about a second. Waiting the full trial
#: timeout on each probe turns this pass into minutes of silence for no extra certainty.
PROBE_TIMEOUT = 6.0

def _applied_modes(results: list[Result]) -> list[Any]:
    """Mode values the device accepted during the run."""
    return [r.written for r in results if r.parameter == "modes.mode" and r.ok]


async def restore(
    rest: MysaRest, device_id: str, trial: Trial, settle: float, timeout: float
) -> bool:
    parameter = trial.parameter
    restore = Write(parameter.section, {parameter.field: trial.original})
    try:
        await rest.update_state(device_id, restore.payload())
    except MysaError:
        return False
    return await await_value(
        rest, device_id, parameter.section, parameter.field, trial.original, settle, timeout
    )


async def await_value(
    rest: MysaRest,
    device_id: str,
    section: str,
    field_name: str,
    expected: Any,
    settle: float,
    timeout: float,
) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        await asyncio.sleep(settle)
        batch = await rest.get_state_batch([device_id])
        if close(in_force(batch, device_id, section, field_name), expected):
            return True
    return False


async def retry_under_modes(
    rest: MysaRest,
    device_id: str,
    trials: list[Trial],
    results: list[Result],
    settle: float,
    timeout: float,
    announce: Callable[[str], None],
    probe_timeout: float = PROBE_TIMEOUT,
) -> list[Result]:
    """Re-attempt what the device declined, once under each mode it accepted.

    A parameter a device ignores is usually one its current mode does not select. Which
    modes do select it is a fact about the device, and this is how it is established.
    """
    modes = _applied_modes(results)
    pending = [r for r in results if r.status == NOT_APPLIED and r.parameter != "modes.mode"]
    if not modes or not pending:
        return results

    by_name = {t.parameter.name: t for t in trials}
    mode_trial = by_name.get("modes.mode")
    if mode_trial is None:
        return results

    found: dict[str, list[Any]] = {}
    estimate = len(modes) * (1 + len(pending)) * probe_timeout
    announce(
        f"  retrying {len(pending)} declined parameter(s) under {len(modes)} mode(s); "
        f"up to {estimate / 60:.0f} min"
    )
    try:
        for mode in modes:
            if not await _set_mode(rest, device_id, mode_trial, mode, settle, probe_timeout):
                announce(f"    mode {mode}: not applied, skipping")
                continue
            announce(f"    mode {mode}:")
            for result in pending:
                trial = by_name.get(result.parameter)
                if trial is None:
                    continue
                applies = await _applies(rest, device_id, trial, settle, probe_timeout)
                announce(
                    f"      {trial.parameter.name:<34} "
                    f"{'applies' if applies else 'declined'}"
                )
                if applies:
                    found.setdefault(result.parameter, []).append(mode)
                    await restore(rest, device_id, trial, settle, probe_timeout)
    finally:
        # An interrupt here would otherwise leave the device in a probe mode.
        await _set_mode(rest, device_id, mode_trial, mode_trial.original, settle, timeout)

    updated: list[Result] = []
    for result in results:
        modes_found = found.get(result.parameter)
        if result.status == NOT_APPLIED and modes_found:
            updated.append(
                Result(
                    result.parameter, result.original, result.written, PASSED,
                    "", tuple(modes_found),
                )
            )
        elif result.status == NOT_APPLIED and result.parameter in {r.parameter for r in pending}:
            updated.append(
                Result(
                    result.parameter, result.original, result.written, NOT_APPLIED,
                    f"declined in mode {', '.join(str(m) for m in modes)}",
                )
            )
        else:
            updated.append(result)
    return updated


async def _set_mode(
    rest: MysaRest, device_id: str, trial: Trial, mode: Any, settle: float, timeout: float
) -> bool:
    try:
        await rest.update_state(device_id, Write("modes", {"mode": mode}).payload())
    except MysaError:
        return False
    return await await_value(rest, device_id, "modes", "mode", mode, settle, timeout)


async def _applies(
    rest: MysaRest, device_id: str, trial: Trial, settle: float, timeout: float
) -> bool:
    parameter = trial.parameter
    write = Write(parameter.section, {parameter.field: trial.candidate})
    try:
        await rest.update_state(device_id, write.payload())
    except MysaError:
        return False
    return await await_value(
        rest, device_id, parameter.section, parameter.field, trial.candidate, settle, timeout
    )
