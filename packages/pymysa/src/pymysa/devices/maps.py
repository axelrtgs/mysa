"""Semantic name to state field, per model. See docs/specs/02-devices.md.

Every field here has been seen in a capture from that model. A model reports what it
reports: a name absent from its map reads as None, and no name is defaulted from another
model's document.
"""

from __future__ import annotations

from dataclasses import dataclass

TELEMETRY = "latestTelemetry"
READING = "latestTelemetry.reading"
#: The device record from `/devices`. Read-only: no write path to it is established.
RECORD = "record"


@dataclass(frozen=True)
class Source:
    """Where a semantic value is read from."""

    section: str
    field: str
    #: Key inside the value, where the field holds an object.
    nested: str = ""


def _sources(**pairs: tuple[str, str] | tuple[str, str, str]) -> dict[str, Source]:
    return {name: Source(*parts) for name, parts in pairs.items()}


#: Reported by every model.
SHARED = _sources(
    connected=(TELEMETRY, "isConnected"),
    last_connected=(TELEMETRY, "lastConnected"),
    current_temperature=(READING, "roomTemperature"),
    raw_temperature=(READING, "rawTemperature"),
    humidity=(READING, "humidity"),
    power_consumed=(READING, "powerConsumed"),
    on_time=(READING, "onTime"),
    target_temperature=("targetHeat", "setpoint"),
    min_setpoint=("targetHeat", "lockoutMin"),
    max_setpoint=("targetHeat", "lockoutMax"),
    mode=("modes", "mode"),
    lock=("physicalInterface", "lockout"),
    temperature_format=("physicalInterface", "format"),
    active_brightness=("physicalInterface", "activeIntensity"),
    idle_brightness=("physicalInterface", "idleIntensity"),
    firmware=("identity", "fw"),
    family=("identity", "family"),
)

#: Both baseboards. A BB-V1-0 reports no serial.
_BASEBOARD = SHARED | _sources(
    core_temperature=(READING, "coreTemperature"),
    current=("power", "current"),
    voltage=("power", "voltage"),
    wattage=("power", "wattage"),
    duty_cycle=("power", "dutyCycle"),
    brightness_mode=("physicalInterface", "intensityMode"),
    proximity=("physicalInterface", "wakeOnApproach"),
    heater_type=("bbConfig", "controlType"),
)

BB_V1 = _BASEBOARD | _sources(
    signal_strength=(READING, "rssi"),
    early_on=(RECORD, "schedGlobalOffset"),
)

#: No `rssi` in its telemetry reading, so no signal strength, and no `wattage`: its
#: `power` section is frozen, so the live current and duty cycle come from telemetry and
#: the wattage is derived from volts and amps (spec 02).
BB_V3 = _sources(**{
    name: (source.section, source.field)
    for name, source in _BASEBOARD.items()
    if name != "wattage"
}) | _sources(
    current=(READING, "current"),
    duty_cycle=(READING, "dutyCycle"),
    serial=("identity", "serial"),
    secondary_raw_temperature=(READING, "secondaryRawTemperature"),
    energy=(READING, "energy"),
    fault=("power", "fault"),
    remote_temperature=("tracking", "remoteTemperature"),
    tracking_mode=("tracking", "tracking"),
    ambient_offset=("tracking", "ambientOffset"),
    proximity_sensitivity=("physicalInterface", "woaSensitivity"),
    early_on=("cloudFeatures", "cloudEarlyOn", "enabled"),
)

#: No `power` section, no serial, no energy. `voltage` and `powerConsumed` are reported
#: and deliberately unmapped: the unit is an infrared blaster and measures nothing about
#: the head unit it drives (spec 02).
AC_V1 = _sources(**{
    name: (source.section, source.field)
    for name, source in SHARED.items()
    if name != "power_consumed"
}) | _sources(
    signal_strength=(READING, "rssi"),
    codeset=(RECORD, "CodeNum"),
    remote_brand=(RECORD, "Brand", "Brand"),
    target_temperature_cool=("targetCool", "setpoint"),
    target_temperature_auto=("targetAuto", "setpoint"),
    fan_speed=("modes", "fan_mode"),
    vertical_swing=("modes", "verticalSwingState"),
    horizontal_swing=("modes", "horizontalSwingState"),
    unit_power=("modes", "unitPower"),
    thermostatic=("modes", "isThermostatic"),
)

FIELDS: dict[str, dict[str, Source]] = {
    "BB-V1-0": BB_V1,
    "BB-V3-0": BB_V3,
    "AC-V1-0": AC_V1,
}


def semantics(model: str) -> dict[tuple[str, str], str]:
    """(section, field) to the semantic name a device class reads it as.

    The inverse of the model's field map. The harness uses it to decide how much a
    missing field matters (spec 07): a field nothing reads is informational however
    alarming its name.
    """
    return {
        (source.section, source.field): name
        for name, source in FIELDS.get(model, {}).items()
    }
