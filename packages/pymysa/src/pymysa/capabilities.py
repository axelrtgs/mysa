"""Controls an AC unit's codeset declares. See docs/specs/04-capabilities.md.

An AC controller drives a head unit over infrared using a codeset. What the codeset can
express is what the unit supports, and it does not follow from the state document: a
unit reports `modes.horizontalSwingState` whether or not its remote has the control.
`/capabilities/{device_id}` is the declaration; the state document is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

FAN = "fan"
VERTICAL_SWING = "vertical_swing"
HORIZONTAL_SWING = "horizontal_swing"

#: Codeset key ids for fan speeds. `[inferred]`
FAN_KEYS = frozenset({8, 9, 10, 11})
#: Codeset key ids seen on units with vertical swing. `[observed]`
VERTICAL_SWING_KEYS = frozenset({12, 39, 40, 47})

#: Parameter names gated by a declared control.
GATED: dict[str, str] = {
    "modes.fan_mode": FAN,
    "modes.verticalSwingState": VERTICAL_SWING,
    "modes.horizontalSwingState": HORIZONTAL_SWING,
}


def declared(capabilities: dict[str, Any] | None) -> frozenset[str] | None:
    """Controls the codeset declares, or None when it declares nothing usable.

    None means unknown, not empty: a device with no capability declaration is exercised
    on everything it reports, because there is nothing to gate on.
    """
    if not isinstance(capabilities, dict) or "error" in capabilities:
        return None

    modes = capabilities.get("modes")
    keys = {k for k in capabilities.get("keys", []) if isinstance(k, int)}
    if not isinstance(modes, dict) and not keys:
        return None

    found: set[str] = set()
    if isinstance(modes, dict):
        for entry in modes.values():
            if not isinstance(entry, dict):
                continue
            if entry.get("fanSpeeds"):
                found.add(FAN)
            if entry.get("verticalSwing"):
                found.add(VERTICAL_SWING)
            if entry.get("horizontalSwing"):
                found.add(HORIZONTAL_SWING)

    # Keys are a fallback for the controls they identify. Horizontal swing has no key
    # fallback: absence of a horizontalSwing block means the codeset cannot express it.
    if FAN not in found and keys & FAN_KEYS:
        found.add(FAN)
    if VERTICAL_SWING not in found and keys & VERTICAL_SWING_KEYS:
        found.add(VERTICAL_SWING)
    return frozenset(found)


def gates(parameter: str) -> str | None:
    """The control a parameter needs, if it needs one."""
    return GATED.get(parameter)


#: Capability path to the state field it governs. The two documents use different names.
#: `[inferred]`
CAPABILITY_MAP: dict[str, tuple[str, str]] = {
    "climateControl.mode": ("modes", "mode"),
    "climateControl.heat.setpoint": ("targetHeat", "setpoint"),
    "climateControl.cool.setpoint": ("targetCool", "setpoint"),
    "climateControl.advancedConfig.baseboardHeating.controlType": (
        "bbConfig", "controlType",
    ),
    "sensing.temperature.trackingSensor": ("tracking", "tracking"),
    "sensing.temperature.temperatureOffset": ("tracking", "ambientOffset"),
    "interface.wakeOnApproach": ("physicalInterface", "wakeOnApproach"),
    "interface.lockout": ("physicalInterface", "lockout"),
    "interface.unit": ("physicalInterface", "format"),
    "interface.adaptiveBrightness.intensityMode": ("physicalInterface", "intensityMode"),
    "interface.doCheckmark": ("physicalInterface", "doCheckmark"),
}


@dataclass(frozen=True)
class Setting:
    """What the capability document says about one field."""

    writable: bool
    kind: str
    values: tuple[Any, ...] | None = None


def settings(capabilities: dict[str, Any] | None) -> dict[tuple[str, str], Setting]:
    """Declared settings, keyed by the state field each governs.

    Empty when the device serves no capability document, which is not the same as a
    device that declares nothing writable.
    """
    if not isinstance(capabilities, dict) or "error" in capabilities:
        return {}
    found: dict[tuple[str, str], Setting] = {}
    for path, leaf in _leaves(capabilities.get("features", {})):
        field = CAPABILITY_MAP.get(path)
        if field is None:
            continue
        values = leaf.get("validValues")
        found[field] = Setting(
            writable=bool(leaf.get("userControllable")),
            kind=str(leaf.get("type", "")),
            values=tuple(values) if isinstance(values, list) else None,
        )
    return found


def undeclared(capabilities: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Writable settings the device declares that no state field is mapped to.

    A setting with no state field cannot be exercised: a write to it has nothing to read
    back. The mapping is found by setting it in the app and watching which section moves
    (spec 07), not by guessing a section name.
    """
    if not isinstance(capabilities, dict) or "error" in capabilities:
        return []
    return [
        (path, str(leaf.get("type", "")))
        for path, leaf in _leaves(capabilities.get("features", {}))
        if leaf.get("userControllable") and path not in CAPABILITY_MAP
    ]


def _leaves(node: Any, prefix: str = "") -> list[tuple[str, dict[str, Any]]]:
    """Every declaration under `features`, by dotted path."""
    if not isinstance(node, dict):
        return []
    if "userControllable" in node:
        return [(prefix, node)]
    found: list[tuple[str, dict[str, Any]]] = []
    for key, value in node.items():
        found += _leaves(value, f"{prefix}.{key}" if prefix else key)
    return found


class Capability(Enum):
    """What a device can do, as the SDK exposes it. See docs/specs/09-sdk-surface.md.

    Declared from the capability document where one is served, from the codeset for AC
    units, and otherwise from the fields the device reports. A capability whose option
    set resolves empty is not declared.
    """

    HEAT = "heat"
    COOL = "cool"
    FAN = "fan"
    VERTICAL_SWING = "vertical_swing"
    HORIZONTAL_SWING = "horizontal_swing"
    CURRENT = "current"
    ENERGY = "energy"
    LOCK = "lock"
    PROXIMITY = "proximity"
    BRIGHTNESS = "brightness"
    ADAPTIVE_BRIGHTNESS = "adaptive_brightness"
    TEMPERATURE_FORMAT = "temperature_format"
    SENSOR_MODE = "sensor_mode"
    SETPOINT_LIMITS = "setpoint_limits"
    SCHEDULE = "schedule"
    THERMOSTATIC = "thermostatic"
    HEATER_TYPE = "heater_type"
    TEMPERATURE_OFFSET = "temperature_offset"
    EARLY_ON = "early_on"


#: Codeset control name to the capability it declares.
CONTROL_CAPABILITY: dict[str, Capability] = {
    FAN: Capability.FAN,
    VERTICAL_SWING: Capability.VERTICAL_SWING,
    HORIZONTAL_SWING: Capability.HORIZONTAL_SWING,
}
