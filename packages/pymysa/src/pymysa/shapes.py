"""Declared value shapes. See docs/specs/02-devices.md.

A field is shaped only where its permitted values are established. An unshaped field is
never checked: declaring a range for a field whose real range is unknown produces false
reports, which is worse than no report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Shape:
    """What a field may hold."""

    values: tuple[Any, ...] | None = None
    low: float | None = None
    high: float | None = None
    boolean: bool = False
    #: Fields in the same section carrying the bounds, when the device sets them.
    bounds: tuple[str, str] | None = None

    def describe(self, body: dict[str, Any] | None = None) -> str:
        if self.boolean:
            return "true or false"
        if self.values is not None:
            return "one of " + ", ".join(repr(v) for v in self.values)
        low, high = self.limits(body or {})
        return f"{low}-{high}"

    def limits(self, body: dict[str, Any]) -> tuple[float | None, float | None]:
        if self.bounds is None:
            return self.low, self.high
        low, high = body.get(self.bounds[0]), body.get(self.bounds[1])
        return (
            low if isinstance(low, (int, float)) else self.low,
            high if isinstance(high, (int, float)) else self.high,
        )

    def holds(self, value: Any, body: dict[str, Any] | None = None) -> bool:
        if value is None:
            return True
        if self.boolean:
            return isinstance(value, bool)
        if self.values is not None:
            # `True == 1`, so a bare membership test lets a boolean pass an integer
            # enum. A device switching a 0/1 flag to true/false is a shape change.
            if isinstance(value, bool) and not any(
                isinstance(v, bool) for v in self.values
            ):
                return False
            return value in self.values
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        low, high = self.limits(body or {})
        return (low is None or value >= low) and (high is None or value <= high)


def _enum(*values: Any) -> Shape:
    return Shape(values=values)


def _range(low: float, high: float) -> Shape:
    return Shape(low=low, high=high)


PERCENT = _range(0, 100)
FLAG = _enum(0, 1)

SHAPES: dict[tuple[str, str], Shape] = {
    ("latestTelemetry", "isConnected"): Shape(boolean=True),
    ("modes", "mode"): _enum(0, 1, 3, 4, 7, 8),
    ("modes", "fan_mode"): _enum(0, 1, 2, 3),
    ("modes", "verticalSwingState"): _enum(1, 2),
    ("modes", "horizontalSwingState"): _enum(1, 2),
    ("modes", "unitPower"): _enum(1, 2),
    ("modes", "isThermostatic"): FLAG,
    ("physicalInterface", "format"): _enum("C", "F"),
    #: 0 unlocked, 1 limited, 3 full. Not a flag; see spec 02.
    ("physicalInterface", "lockout"): _enum(0, 1, 3),
    ("physicalInterface", "wakeOnApproach"): FLAG,
    ("physicalInterface", "intensityMode"): _enum(0, 1, 2, 3),
    ("physicalInterface", "doCheckmark"): FLAG,
    ("physicalInterface", "activeIntensity"): PERCENT,
    ("physicalInterface", "idleIntensity"): PERCENT,
    ("physicalInterface", "woaSensitivity"): PERCENT,
    ("power", "dutyCycle"): PERCENT,
    #: The capability document declares six values, not two.
    ("power", "fault"): _enum(0, 1, 2, 3, 4, 5),
    ("targetHeat", "setpoint"): Shape(bounds=("lockoutMin", "lockoutMax")),
    ("targetCool", "setpoint"): Shape(bounds=("lockoutMin", "lockoutMax")),
    ("tracking", "ambientOffset"): _range(-5, 5),
    ("latestTelemetry.reading", "humidity"): PERCENT,
    ("latestTelemetry.reading", "dutyCycle"): PERCENT,
}


def same_kind(value: Any, other: Any) -> bool:
    """Whether two values are the same sort of thing.

    A declaration can name values the state field holds as numbers, and a name written
    where a number belongs is refused by the schema. Comparing kinds catches that before
    anything offers the name as an option or writes it.
    """
    if other is None:
        return True
    if isinstance(other, bool) or isinstance(value, bool):
        return isinstance(value, bool) is isinstance(other, bool)
    if isinstance(other, (int, float)):
        return isinstance(value, (int, float))
    return isinstance(value, type(other))


def shape_of(section: str, field: str) -> Shape | None:
    return SHAPES.get((section, field))
