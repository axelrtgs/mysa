"""Choosing what to write to a device, and what not to.

A device declares what it supports by which sections and fields its own state document
contains. The plan for a device is therefore built from that document, not from a table
keyed by model, so a model nobody has seen is exercised on whatever it reports.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .capabilities import Setting, gates
from .catalogue import (
    CATALOGUE,
    CHOICE,
    NESTED_FLAG,
    NUMERIC,
    TOGGLE,
    Parameter,
)
from .meanings import value_for
from .shapes import same_kind

#: A declared set larger than this is sampled rather than enumerated. Writing all 51
#: valid setpoints establishes nothing that its bounds and midpoint do not.
MAX_DECLARED = 6

__all__ = [
    "CATALOGUE",
    "CHOICE",
    "MAX_DECLARED",
    "NESTED_FLAG",
    "NUMERIC",
    "TOGGLE",
    "Parameter",
    "Trial",
    "candidates",
    "desired",
    "plan",
    "reported",
    "reported_only",
    "untranslated",
]


@dataclass(frozen=True)
class Trial:
    parameter: Parameter
    original: Any
    candidate: Any
    #: (field, required, original) to set before the write and put back after, when the
    #: parameter configures a feature that is currently off.
    enable: tuple[str, Any, Any] | None = None


def reported(document: dict[str, Any], section: str) -> dict[str, Any]:
    body = document.get(section)
    if not isinstance(body, dict):
        return {}
    half = body.get("reported")
    return half if isinstance(half, dict) else body


def desired(document: dict[str, Any], section: str) -> dict[str, Any] | None:
    """The desired half of a section, or None where the section has no shadow pair."""
    body = document.get(section)
    if not isinstance(body, dict):
        return None
    half = body.get("desired")
    return half if isinstance(half, dict) else None


def reported_only(
    document: dict[str, Any], catalogue: Sequence[Parameter] = CATALOGUE
) -> list[str]:
    """Catalogue fields the device reports but carries no desired half for.

    The backend keeps no desired value for them, so a write is accepted and dropped.
    """
    found: list[str] = []
    for parameter in catalogue:
        wanted = desired(document, parameter.section)
        if wanted is None:
            continue
        if parameter.field not in reported(document, parameter.section):
            continue
        if parameter.field not in wanted:
            found.append(parameter.name)
    return found


def plan(
    document: dict[str, Any],
    catalogue: Sequence[Parameter] = CATALOGUE,
    declared: frozenset[str] | None = None,
    settings: dict[tuple[str, str], Setting] | None = None,
    model: str | None = None,
) -> list[Trial]:
    """Trials for the parameters this device reports and declares writable.

    `declared` is the AC codeset control set, or None when nothing is gated on it.
    `settings` is the capability document (spec 04), which names which fields are
    writable and which values they take. Where it covers a field it is authoritative:
    a value outside the declared set is accepted and never applied, and a value invented
    here would look like a broken write path.
    """
    settings = settings or {}
    trials: list[Trial] = []
    for parameter in catalogue:
        if declared is not None:
            gate = gates(parameter.name)
            if gate is not None and gate not in declared:
                continue
        setting = settings.get((parameter.section, parameter.field))
        if setting is not None and not setting.writable:
            continue
        body = reported(document, parameter.section)
        if parameter.field not in body:
            continue
        wanted = desired(document, parameter.section)
        if wanted is not None and parameter.field not in wanted:
            # Reported with no desired half: the backend holds no setpoint for it, and
            # the write is accepted and dropped. See spec 02.
            continue
        original = body[parameter.field]
        enable = _enable(parameter, body)
        trials += [
            Trial(parameter, original, value, enable)
            for value in candidates(parameter, original, body, setting, model)
        ]
    return trials


def _enable(parameter: Parameter, body: dict[str, Any]) -> tuple[str, Any, Any] | None:
    """What to switch on before writing this parameter, if anything.

    A setting that configures a feature is refused while the feature is off, with a
    message that reads as though the hardware lacks it.
    """
    if parameter.requires is None:
        return None
    field, required = parameter.requires
    if field not in body or body[field] == required:
        return None
    return (field, required, body[field])


def candidates(
    parameter: Parameter,
    original: Any,
    body: dict[str, Any],
    setting: Setting | None = None,
    model: str | None = None,
) -> list[Any]:
    """Every value worth writing, given what the device currently holds.

    A parameter drawn from a fixed set yields all the others, so each value is written
    from whatever state the device was found in - a device found off is switched on, and
    one found on is switched off. An empty list is a skip, not a failure: a single-valued
    field has nothing to exercise.
    """
    if setting is not None and setting.values:
        return _from_declaration(parameter, original, body, setting, model)

    if parameter.kind == TOGGLE:
        if isinstance(original, bool):
            return [not original]
        return [0 if original else 1]

    if parameter.kind == NESTED_FLAG:
        if not isinstance(original, dict) or parameter.nested not in original:
            return []
        return [{parameter.nested: not original[parameter.nested]}]

    if parameter.kind == CHOICE:
        # A device already outside its declared set is not one to guess at.
        if original not in parameter.choices:
            return []
        return [choice for choice in parameter.choices if choice != original]

    if not isinstance(original, (int, float)):
        return []
    low, high = _range(parameter, body)
    for value in (original + parameter.step, original - parameter.step):
        if (low is None or value >= low) and (high is None or value <= high):
            return [type(original)(value) if isinstance(original, int) else value]
    return []


def _from_declaration(
    parameter: Parameter,
    original: Any,
    body: dict[str, Any],
    setting: Setting,
    model: str | None = None,
) -> list[Any]:
    """Candidates drawn from the capability document.

    The declared set is the hardware's; a device's own lockout range narrows it further,
    and a value outside that range is refused by the schema.
    """
    values = [
        value_for(parameter.section, parameter.field, value, model)
        for value in setting.values or ()
    ]
    # A declaration can name values the state field holds as numbers
    # (`sensing.temperature.trackingSensor` declares "internal" and "remote" for a field
    # holding 0). Untranslated, the name is refused by the schema, which reads as a
    # broken write path rather than a missing map.
    values = [value for value in values if same_kind(value, original)]
    low, high = _range(parameter, body)
    numeric = [v for v in values if isinstance(v, (int, float))]
    if numeric and len(numeric) == len(values):
        values = [
            v for v in numeric
            if (low is None or v >= low) and (high is None or v <= high)
        ]

    values = [v for v in values if v != original]
    if len(values) <= MAX_DECLARED:
        return values
    return _sample(values)


def untranslated(
    document: dict[str, Any],
    settings: dict[tuple[str, str], Setting] | None = None,
    model: str | None = None,
    catalogue: Sequence[Parameter] = CATALOGUE,
) -> list[str]:
    """Writable fields whose declared values no map translates.

    Reported rather than written: naming them takes watching the app set each one, which
    is the same evidence every other meaning rests on.
    """
    settings = settings or {}
    found: list[str] = []
    for parameter in catalogue:
        setting = settings.get((parameter.section, parameter.field))
        if setting is None or not setting.writable or not setting.values:
            continue
        body = reported(document, parameter.section)
        if parameter.field not in body:
            continue
        wanted = desired(document, parameter.section)
        if wanted is not None and parameter.field not in wanted:
            # Reported with no desired half: the backend holds no setpoint for it, and
            # the write is accepted and dropped. See spec 02.
            continue
        original = body[parameter.field]
        translated = [
            value_for(parameter.section, parameter.field, value, model)
            for value in setting.values
        ]
        if translated and not any(same_kind(v, original) for v in translated):
            found.append(f"{parameter.name} (declares {', '.join(map(str, setting.values))})")
    return found


def _sample(values: list[Any]) -> list[Any]:
    """The bounds and the midpoint of a large declared set, in declaration order."""
    chosen = {0, len(values) // 2, len(values) - 1}
    return [values[index] for index in sorted(chosen)]


def _range(parameter: Parameter, body: dict[str, Any]) -> tuple[float | None, float | None]:
    if parameter.bounds is None:
        if parameter.unbounded:
            return (None, None)
        # What remains without declared bounds is a percentage.
        return (0, 100)
    low_field, high_field = parameter.bounds
    low, high = body.get(low_field), body.get(high_field)
    return (
        low if isinstance(low, (int, float)) else None,
        high if isinstance(high, (int, float)) else None,
    )
