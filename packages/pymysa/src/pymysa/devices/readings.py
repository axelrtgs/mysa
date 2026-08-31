"""Semantic values a device exposes. See docs/specs/09-sdk-surface.md.

Every property resolves through the model's field map. A model that does not report a
field reads `None` for it: absent values are never defaulted or estimated, and `None`
and `0` stay distinct (spec 00).

Enumerated fields are exposed twice: by name where a name is established, and as the
wire value. A value nothing names reads as `None` by name and as its number by value, so
an unmapped value is visible rather than silently absent.
"""

from __future__ import annotations

from typing import Any


class Readings:
    """Semantic properties. Mixed into `MysaDevice`, which supplies the lookups."""

    def _value(self, name: str) -> Any:  # pragma: no cover - supplied by MysaDevice
        raise NotImplementedError

    def _named(self, name: str) -> str | None:  # pragma: no cover - as above
        raise NotImplementedError

    def _number(self, name: str) -> float | None:  # pragma: no cover - as above
        raise NotImplementedError

    def _integer(self, name: str) -> int | None:  # pragma: no cover - as above
        raise NotImplementedError

    def _flag(self, name: str) -> bool | None:  # pragma: no cover - as above
        raise NotImplementedError

    # Temperature and humidity.

    @property
    def current_temperature(self) -> float | None:
        """Room temperature in degrees Celsius."""
        return self._number("current_temperature")

    @property
    def raw_temperature(self) -> float | None:
        """The sensor reading before the device's own correction."""
        return self._number("raw_temperature")

    @property
    def core_temperature(self) -> float | None:
        """Temperature inside the enclosure, which runs above the room."""
        return self._number("core_temperature")

    @property
    def secondary_raw_temperature(self) -> float | None:
        return self._number("secondary_raw_temperature")

    @property
    def remote_temperature(self) -> float | None:
        """A remote sensor's reading, where one is paired."""
        return self._number("remote_temperature")

    @property
    def ambient_offset(self) -> float | None:
        """The correction applied to the room reading, in degrees."""
        return self._number("ambient_offset")

    @property
    def humidity(self) -> float | None:
        return self._number("humidity")

    # Setpoints.

    @property
    def target_temperature(self) -> float | None:
        """The setpoint the current mode selects, in degrees Celsius."""
        return self._number(self.active_setpoint)

    @property
    def active_setpoint(self) -> str:
        """Which setpoint the device is acting on, as a semantic name.

        A unit carrying more than one setpoint section applies the one its mode selects,
        and accepts a write to the others without applying it (spec 03).
        """
        by_mode = {"cool": "target_temperature_cool", "auto": "target_temperature_auto"}
        wanted = by_mode.get(self.mode or "", "target_temperature")
        return wanted if self._value(wanted) is not None else "target_temperature"

    @property
    def heat_setpoint(self) -> float | None:
        return self._number("target_temperature")

    @property
    def cool_setpoint(self) -> float | None:
        return self._number("target_temperature_cool")

    @property
    def auto_setpoint(self) -> float | None:
        return self._number("target_temperature_auto")

    @property
    def min_setpoint(self) -> float | None:
        """The device's own lower limit, which is narrower than the hardware range."""
        return self._number("min_setpoint")

    @property
    def max_setpoint(self) -> float | None:
        return self._number("max_setpoint")

    # Mode and air handling.

    @property
    def mode(self) -> str | None:
        return self._named("mode")

    @property
    def mode_value(self) -> int | None:
        return self._integer("mode")

    @property
    def fan_speed(self) -> str | None:
        return self._named("fan_speed")

    @property
    def fan_speed_value(self) -> int | None:
        return self._integer("fan_speed")

    @property
    def vertical_swing(self) -> str | None:
        return self._named("vertical_swing")

    @property
    def vertical_swing_value(self) -> int | None:
        return self._integer("vertical_swing")

    @property
    def horizontal_swing(self) -> str | None:
        return self._named("horizontal_swing")

    @property
    def horizontal_swing_value(self) -> int | None:
        return self._integer("horizontal_swing")

    @property
    def unit_power(self) -> int | None:
        """Reported only; the backend holds no desired value for it (spec 02)."""
        return self._integer("unit_power")

    @property
    def thermostatic(self) -> bool | None:
        """Whether the unit follows a setpoint rather than running its own program."""
        return self._flag("thermostatic")

    # Electrical.

    @property
    def current(self) -> float | None:
        return self._number("current")

    @property
    def voltage(self) -> float | None:
        return self._number("voltage")

    @property
    def wattage(self) -> float | None:
        return self._number("wattage")

    @property
    def power(self) -> float | None:
        """Watts now.

        The device's own measurement where it comes from a section that moves, and
        otherwise volts times amps, which is what a BB-V3-0's app does: its `power`
        section is frozen and its telemetry carries the live current (spec 02).
        """
        wattage = self._number("wattage")
        if wattage is not None:
            return wattage
        volts, milliamps = self._number("voltage"), self._number("current")
        if volts is None or milliamps is None:
            return None
        return round(volts * milliamps / 1000, 1)

    @property
    def energy(self) -> float | None:
        return self._number("energy")

    @property
    def power_consumed(self) -> float | None:
        return self._number("power_consumed")

    @property
    def duty_cycle(self) -> float | None:
        """Percentage of the cycle the element was on."""
        return self._number("duty_cycle")

    @property
    def on_time(self) -> float | None:
        return self._number("on_time")

    @property
    def fault(self) -> int | None:
        return self._integer("fault")

    # Interface.

    @property
    def lock(self) -> str | None:
        return self._named("lock")

    @property
    def lock_value(self) -> int | None:
        return self._integer("lock")

    @property
    def temperature_format(self) -> str | None:
        """`celsius` or `fahrenheit`. The display unit; values are always Celsius."""
        return self._named("temperature_format")

    @property
    def active_brightness(self) -> int | None:
        return self._integer("active_brightness")

    @property
    def idle_brightness(self) -> int | None:
        return self._integer("idle_brightness")

    @property
    def brightness_mode(self) -> str | None:
        return self._named("brightness_mode")

    @property
    def proximity(self) -> bool | None:
        """Whether the display wakes on approach."""
        return self._flag("proximity")

    @property
    def proximity_sensitivity(self) -> int | None:
        return self._integer("proximity_sensitivity")

    # Configuration and diagnostics.

    @property
    def heater_type(self) -> str | None:
        """The load the device is driving. The values differ by model (spec 02)."""
        return self._named("heater_type")

    @property
    def tracking_mode(self) -> int | None:
        """Which sensor the device tracks. No name is established for either value."""
        return self._integer("tracking_mode")

    @property
    def early_on(self) -> bool | None:
        """Whether the backend starts heating ahead of a scheduled setpoint."""
        return self._flag("early_on")

    @property
    def codeset(self) -> str | None:
        """The codeset an AC controller drives its head unit with."""
        value = self._value("codeset")
        return str(value) if value is not None else None

    @property
    def remote_brand(self) -> str | None:
        """The head unit's brand, as the codeset names it."""
        value = self._value("remote_brand")
        return value if isinstance(value, str) else None

    @property
    def signal_strength(self) -> int | None:
        """RSSI in dBm. A BB-V3-0 reports none."""
        return self._integer("signal_strength")

    @property
    def last_connected(self) -> int | None:
        return self._integer("last_connected")
