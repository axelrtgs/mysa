"""What a reported value means. See docs/specs/02-devices.md.

Only mappings established by watching a device change are recorded. A value absent from
a map is unmapped, and the harness lists it rather than guessing at it.

Meanings can be per model: `bbConfig.controlType` takes 0, 4, 5, 6, 7 on a BB-V1-0 and
0, 1, 2 on a BB-V3-0, so the names of one are not the names of the other.
"""

from __future__ import annotations

from typing import Any

#: (model or None for any, section, field) -> value -> name.
MEANINGS: dict[tuple[str | None, str, str], dict[Any, str]] = {
    #: Named by selecting each mode in the app and reading the value back on an AC-V1-0,
    #: which is the only model that offers them all. 2, 5 and 6 are not modes: 2 is
    #: refused by the schema and neither of the others was ever produced.
    (None, "modes", "mode"): {
        0: "off",
        1: "auto",
        3: "cool",
        4: "heat",
        7: "fan only",
        8: "dry",
    },
    (None, "modes", "fan_mode"): {0: "auto", 1: "low", 2: "medium", 3: "high"},
    (None, "modes", "verticalSwingState"): {1: "off", 2: "on"},
    (None, "physicalInterface", "format"): {"C": "celsius", "F": "fahrenheit"},
    (None, "physicalInterface", "lockout"): {0: "unlocked", 3: "full"},
    ("BB-V3-0", "physicalInterface", "lockout"): {
        0: "unlocked",
        1: "limited to the lockout range",
        3: "full",
    },
    (None, "physicalInterface", "wakeOnApproach"): {0: "off", 1: "on"},
    (None, "physicalInterface", "intensityMode"): {0: "fixed", 1: "adaptive"},
    ("BB-V1-0", "bbConfig", "controlType"): {
        0: "baseboard",
        4: "radiant",
        5: "fan forced, short cycle",
        6: "fan forced, medium cycle",
        7: "fan forced, long cycle",
    },
    # The same field, a different set. A shared map would name 1 "radiant".
    ("BB-V3-0", "bbConfig", "controlType"): {
        0: "baseboard",
        1: "fan forced",
        2: "radiant",
    },
}


def _map(model: str | None, section: str, field: str) -> dict[Any, str]:
    """The model's own map where it has one, otherwise the shared map."""
    specific = MEANINGS.get((model, section, field)) if model else None
    return specific if specific is not None else MEANINGS.get((None, section, field), {})


def name_of(section: str, field: str, value: Any, model: str | None = None) -> str | None:
    """The established name for a value, or None when it is unmapped.

    Not every value is a scalar: `cloudFeatures.cloudEarlyOn` holds `{"enabled": bool}`,
    which cannot be a dictionary key.
    """
    try:
        return _map(model, section, field).get(value)
    except TypeError:
        return None


def value_for(section: str, field: str, name: Any, model: str | None = None) -> Any:
    """The value a declared name corresponds to.

    A capability document declares `climateControl.mode` as `off` and `heat`; the state
    field holds integers. Returns the name unchanged when nothing maps it, so a device
    declaring values that are already values passes through.
    """
    for value, known in _map(model, section, field).items():
        if known == name:
            return value
    return name


def is_mapped_field(section: str, field: str, model: str | None = None) -> bool:
    """Whether this field's values are names at all.

    True when any model maps it, not just this one. A BB-V3-0 reporting
    `bbConfig.controlType` 1 has an unnamed value worth listing, because the field is
    known to carry names even though that model's are not established.

    A field nothing maps is not a field with unknown values; it is a field whose values
    are not names, and a setpoint is never unmapped.
    """
    return any(key[1:] == (section, field) for key in MEANINGS)


def unmapped(
    section: str, body: dict[str, Any], model: str | None = None
) -> list[tuple[str, Any]]:
    """Values in a section that have no established name."""
    return [
        (field, value)
        for field, value in sorted(body.items(), key=lambda item: item[0])
        if is_mapped_field(section, field, model)
        and name_of(section, field, value, model) is None
    ]
