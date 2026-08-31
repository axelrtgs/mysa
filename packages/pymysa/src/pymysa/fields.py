"""Semantic field names and their criticality.

Criticality is a property of the role, not of a model: a thermostat that cannot report
its target temperature is broken whatever it is. Device classes map these names onto
their own sections and keys; nothing here knows about a model.
"""

from __future__ import annotations

from enum import Enum


class Criticality(Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    INFORMATIONAL = "informational"


#: Without one of these the climate entity cannot function.
CRITICAL: frozenset[str] = frozenset({
    "current_temperature", "target_temperature", "mode", "connected",
})

#: A control or measurement is lost; the device still heats or cools.
IMPORTANT: frozenset[str] = frozenset({
    "humidity", "min_setpoint", "max_setpoint", "fan_speed", "vertical_swing",
    "horizontal_swing", "unit_power", "lock", "brightness", "temperature_format",
    "current", "voltage", "wattage", "energy", "power_consumed",
})


def criticality(semantic: str | None) -> Criticality:
    """Criticality of a semantic name. An unmapped field is informational."""
    if semantic in CRITICAL:
        return Criticality.CRITICAL
    if semantic in IMPORTANT:
        return Criticality.IMPORTANT
    return Criticality.INFORMATIONAL
