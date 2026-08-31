"""What a device declares it can do. See docs/specs/04-capabilities.md.

Three sources, in order: the capability document where the device serves one, the
codeset declaration for AC units, and otherwise the fields the device reports. A
capability whose option set resolves empty is not declared.
"""

from __future__ import annotations

from typing import Any

from ..capabilities import CONTROL_CAPABILITY, Capability
from ..meanings import name_of, value_for
from ..shapes import same_kind
from .maps import Source

#: Modes a model has been seen to accept, where it serves no capability document.
#: An AC-V1-0 returns 404 for one (spec 04). `[observed]`
OBSERVED_MODES: dict[str, tuple[int, ...]] = {"AC-V1-0": (0, 1, 3, 4, 7, 8)}

#: The resolution a setpoint is accepted at, on every model. Both baseboards declare
#: `climateControl.heat.setpoint` as 5, 5.5, 6 ... 30 (spec 04); an AC unit declares no
#: step and is written at the same resolution. `[observed]`
SETPOINT_STEP = 0.5

#: The bounds a section reports for its own setpoint.
LOCKOUT = ("lockoutMin", "lockoutMax")


class Declaration:
    """Capability derivation. Mixed into `MysaDevice`, which supplies the lookups."""

    _settings: dict[tuple[str, str], Any]
    _declared: frozenset[str] | None
    _document: dict[str, Any]

    @property
    def model(self) -> str:  # pragma: no cover - supplied by MysaDevice
        raise NotImplementedError

    _record: dict[str, Any]

    def _source(self, name: str) -> Source | None:  # pragma: no cover - MysaDevice
        raise NotImplementedError

    def _value(self, name: str) -> Any:  # pragma: no cover - MysaDevice
        raise NotImplementedError

    def _reported(self, section: str, field: str) -> Any:  # pragma: no cover - MysaDevice
        raise NotImplementedError

    @property
    def active_setpoint(self) -> str:  # pragma: no cover - Readings
        raise NotImplementedError

    # Setpoint bounds.

    @property
    def setpoint_step(self) -> float:
        """The resolution a setpoint is accepted at."""
        return SETPOINT_STEP

    @property
    def setpoint_range(self) -> tuple[float, float] | None:
        """The bounds a setpoint write must fall inside, or None where none is served.

        Follows the mode, as `set_temperature` does (spec 03): the bounds belong to the
        section being written. An AC unit's `targetCool` carries no lockout pair while
        its `targetHeat` carries one, and bounding a cool setpoint by the heat section's
        limits would refuse setpoints the device accepts.
        """
        source = self._source(self.active_setpoint)
        if source is None:
            return None
        return self._lockout_range(source.section) or self._declared_range(source)

    def _lockout_range(self, section: str) -> tuple[float, float] | None:
        """The user-set limit the section reports, where it reports one."""
        low = _measure(self._reported(section, LOCKOUT[0]))
        high = _measure(self._reported(section, LOCKOUT[1]))
        if low is None or high is None:
            return None
        return low, high

    def _declared_range(self, source: Source) -> tuple[float, float] | None:
        """The range the device declares: the capability document, or the codeset."""
        setting = self._settings.get((source.section, source.field))
        values = [_measure(value) for value in setting.values or ()] if setting else []
        numbers = [value for value in values if value is not None]
        if numbers:
            return min(numbers), max(numbers)
        caps = self._record.get("SupportedCaps")
        span = caps.get("tempRange") if isinstance(caps, dict) else None
        if isinstance(span, list) and len(span) == 2:
            low, high = _measure(span[0]), _measure(span[1])
            if low is not None and high is not None:
                return low, high
        return None

    # Capabilities.

    @property
    def capabilities(self) -> frozenset[Capability]:
        found: set[Capability] = set()
        if self._has("target_temperature"):
            found.add(Capability.HEAT)
        if self._has("target_temperature_cool"):
            found.add(Capability.COOL)
        found |= self._codeset_capabilities()
        if self._has("current"):
            found.add(Capability.CURRENT)
        if self._has("energy"):
            found.add(Capability.ENERGY)
        if self._offers("lock"):
            found.add(Capability.LOCK)
        if self._controls("proximity"):
            found.add(Capability.PROXIMITY)
        if self._controls("active_brightness") or self._controls("idle_brightness"):
            found.add(Capability.BRIGHTNESS)
        if self._offers("temperature_format"):
            found.add(Capability.TEMPERATURE_FORMAT)
        if self._offers("tracking_mode"):
            found.add(Capability.SENSOR_MODE)
        if self._controls("min_setpoint") and self._controls("max_setpoint"):
            found.add(Capability.SETPOINT_LIMITS)
        if self._document.get("schedule"):
            found.add(Capability.SCHEDULE)
        return frozenset(found)

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def _codeset_capabilities(self) -> set[Capability]:
        """Fan and swing, which an AC's codeset declares rather than its state document.

        A unit reports `modes.horizontalSwingState` whether or not its remote has the
        control (spec 04), so presence is not a declaration. Where nothing declares -
        a device with no codeset block - presence is all there is.
        """
        if self._declared is None:
            return {
                capability
                for name, capability in (
                    ("fan_speed", Capability.FAN),
                    ("vertical_swing", Capability.VERTICAL_SWING),
                    ("horizontal_swing", Capability.HORIZONTAL_SWING),
                )
                if self._offers(name)
            }
        return {
            CONTROL_CAPABILITY[control]
            for control in self._declared
            if control in CONTROL_CAPABILITY
            and self._offers(_CONTROL_FIELD[CONTROL_CAPABILITY[control]])
        }

    def _offers(self, name: str) -> bool:
        """Writable, and with more than one value to choose between.

        A control with one option is not a control. A BB-V1-0 declares `trackingSensor`
        writable with `internal` as its only value, and a BB-V3-0 declares two whose
        numbers are not established (spec 03) - neither is something to expose.
        """
        return self._controls(name) and len(self._option_values(name)) > 1

    def _has(self, name: str) -> bool:
        return self._value(name) is not None

    def _controls(self, name: str) -> bool:
        """Whether the device reports this field and will accept a write to it."""
        source = self._source(name)
        if source is None or not self._has(name):
            return False
        setting = self._settings.get((source.section, source.field))
        if setting is not None:
            return bool(setting.writable)
        return self._in_desired(source.section, source.field)

    def _in_desired(self, section: str, field: str) -> bool:
        """A field reported with no desired half is not writable (spec 02).

        A section with no desired half at all is flat, and says nothing either way.
        """
        body = self._document.get(section)
        if not isinstance(body, dict):
            return False
        wanted = body.get("desired")
        return field in wanted if isinstance(wanted, dict) else True

    def _declared_values(self, name: str) -> tuple[Any, ...]:
        source = self._source(name)
        if source is None:
            return ()
        setting = self._settings.get((source.section, source.field))
        return setting.values or () if setting else ()

    def options(self, capability: Capability) -> tuple[str, ...]:
        """The values a control accepts, by name where names are established."""
        name = _CONTROL_FIELD.get(capability)
        if name is None or not self.supports(capability):
            return ()
        source = self._source(name)
        if source is None:
            return ()
        return tuple(
            name_of(source.section, source.field, value, self.model) or str(value)
            for value in self._option_values(name)
        )

    @property
    def modes(self) -> tuple[str, ...]:
        """The modes this device accepts, by name. Always contains the reported mode."""
        if self._source("mode") is None:
            return ()
        return tuple(
            name_of("modes", "mode", value, self.model) or str(value)
            for value in self._option_values("mode")
        )

    def _option_values(self, name: str) -> list[Any]:
        """The wire values a control accepts, in declaration order.

        A capability document declares names - `climateControl.mode` as `off` and `heat`
        - where the state field holds numbers, so the declaration is translated before
        anything compares it to what the device reports.
        """
        source = self._source(name)
        if source is None:
            return []
        values = [
            value_for(source.section, source.field, value, self.model)
            for value in self._declared_values(name)
        ]
        if not values and name == "mode":
            # Model-keyed: the modes one model takes are not another's.
            values = list(OBSERVED_MODES.get(self.model, ()))
        elif not values:
            values = list(OBSERVED_OPTIONS.get(name, ()))
        current = self._value(name)
        # A declared value the field could not hold is not an option: offering it builds
        # a control whose every selection the backend refuses.
        values = [value for value in values if same_kind(value, current)]
        if current is not None and current not in values:
            values.append(current)
        return list(dict.fromkeys(values))


def _measure(value: Any) -> float | None:
    """A number, and not a boolean wearing one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


#: The semantic field behind each capability's option list.
_CONTROL_FIELD: dict[Capability, str] = {
    Capability.FAN: "fan_speed",
    Capability.VERTICAL_SWING: "vertical_swing",
    Capability.HORIZONTAL_SWING: "horizontal_swing",
    Capability.LOCK: "lock",
    Capability.TEMPERATURE_FORMAT: "temperature_format",
    Capability.SENSOR_MODE: "tracking_mode",
}

#: Sets a device does not declare and that are established by observation (spec 02).
#: An AC-V1-0 serves no capability document, so its controls have only these.
OBSERVED_OPTIONS: dict[str, tuple[Any, ...]] = {
    "fan_speed": (0, 1, 2, 3),
    "vertical_swing": (1, 2),
    "horizontal_swing": (1, 2),
    "temperature_format": ("C", "F"),
    # 1 is a BB-V3-0 state. An AC-V1-0 accepts the write and never applies it.
    "lock": (0, 3),
}
