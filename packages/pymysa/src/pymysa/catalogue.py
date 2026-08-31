"""The writable parameters a run knows about. See docs/specs/03-writes.md.

Data only: which fields exist, what shape their values take, and what has to hold for a
write to be accepted. How a value is chosen for one is in `pymysa.parameters`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

NUMERIC = "numeric"
TOGGLE = "toggle"
CHOICE = "choice"
#: A boolean inside a one-key object, as `cloudFeatures.cloudEarlyOn` carries it.
NESTED_FLAG = "nested_flag"


@dataclass(frozen=True)
class Parameter:
    """One writable field.

    `bounds` names the fields in the same section that carry the permitted range. The
    backend validates against them and rejects an out-of-range write, so honouring them
    keeps a run to real failures rather than expected ones.
    """

    section: str
    field: str
    kind: str
    step: float = 1.0
    bounds: tuple[str, str] | None = None
    choices: Sequence[Any] = ()
    #: The value is not a percentage; step from it without clamping to 0-100.
    unbounded: bool = False
    #: Key inside the object, for NESTED_FLAG.
    nested: str = ""
    #: (field, value) in the same section that must hold for this write to be accepted.
    requires: tuple[str, Any] | None = None

    @property
    def name(self) -> str:
        return f"{self.section}.{self.field}"


CATALOGUE: tuple[Parameter, ...] = (
    # Setpoints. Which one a device applies follows its mode; see spec 03.
    Parameter("targetHeat", "setpoint", NUMERIC, bounds=("lockoutMin", "lockoutMax")),
    Parameter("targetCool", "setpoint", NUMERIC, bounds=("lockoutMin", "lockoutMax")),
    Parameter("targetAuto", "setpoint", NUMERIC, bounds=("lockoutMin", "lockoutMax")),
    Parameter("modes", "fan_mode", CHOICE, choices=(0, 1, 2, 3)),
    Parameter("modes", "verticalSwingState", CHOICE, choices=(1, 2)),
    Parameter("modes", "horizontalSwingState", CHOICE, choices=(1, 2)),
    Parameter("modes", "isThermostatic", TOGGLE),
    Parameter("modes", "lockoutModes", NUMERIC, step=1),
    # Display and interface.
    Parameter("physicalInterface", "lockout", TOGGLE),
    Parameter("physicalInterface", "wakeOnApproach", TOGGLE),
    # `doCheckmark` is deliberately absent: it triggers a display animation and is never
    # held, so a read-back can only ever report it as not applied. See spec 02.
    Parameter("physicalInterface", "format", CHOICE, choices=("C", "F")),
    Parameter("physicalInterface", "intensityMode", NUMERIC, step=1),
    Parameter("physicalInterface", "activeIntensity", NUMERIC, step=10),
    Parameter("physicalInterface", "idleIntensity", NUMERIC, step=10),
    Parameter(
        "physicalInterface", "woaSensitivity", NUMERIC, step=10,
        requires=("wakeOnApproach", 1),
    ),
    Parameter(
        "physicalInterface", "darkRoomLevel", NUMERIC, step=1, unbounded=True,
        requires=("intensityMode", 1),
    ),
    Parameter(
        "physicalInterface", "brightRoomLevel", NUMERIC, step=10, unbounded=True,
        requires=("intensityMode", 1),
    ),
    # Heater configuration.
    Parameter("bbConfig", "controlType", NUMERIC, step=1, unbounded=True),
    Parameter("bbConfig", "hysteresisMinSwitchMinutes", NUMERIC, step=1, unbounded=True),
    Parameter("bbConfig", "hysteresisBandLow", NUMERIC, step=1, unbounded=True),
    Parameter("bbConfig", "hysteresisBandHigh", NUMERIC, step=1, unbounded=True),
    # Sensor tracking.
    Parameter("tracking", "tracking", NUMERIC, step=1, unbounded=True),
    Parameter("tracking", "trackingFallback", NUMERIC, step=1, unbounded=True),
    Parameter("tracking", "ambientOffset", NUMERIC, step=1, unbounded=True),
    Parameter("tracking", "remoteTTL", NUMERIC, step=60, unbounded=True),
    # Backend features. `schedule.holding` is deliberately absent: ending a hold is a
    # write the state document cannot undo, so exercising it changes the account. See
    # spec 08.
    Parameter("cloudFeatures", "cloudEarlyOn", NESTED_FLAG, nested="enabled"),
    # Last: these change how everything above behaves, and originals are only written
    # back once per device, so anything after them would run in an arbitrary state.
    Parameter("modes", "unitPower", CHOICE, choices=(1, 2)),
    # 2 is refused by the schema; 5 and 6 were never produced by any device.
    Parameter("modes", "mode", CHOICE, choices=(0, 1, 3, 4, 7, 8)),
)
