"""The thermostat. See docs/specs/06-ha-entities.md."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pymysa import Capability, MysaDevice

from .coordinator import MysaConfigEntry, MysaCoordinator
from .entity import MysaEntity

#: Mysa's mode names (spec 02) to Home Assistant's. A value with no established name is
#: not offered: it would be a mode the user could select and nothing could carry out.
HVAC_MODES: dict[str, HVACMode] = {
    "off": HVACMode.OFF,
    "auto": HVACMode.AUTO,
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "fan only": HVACMode.FAN_ONLY,
    "dry": HVACMode.DRY,
}
MYSA_MODES: dict[HVACMode, str] = {mode: name for name, mode in HVAC_MODES.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MysaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MysaClimate(coordinator, device)
        for device in coordinator.account.devices.values()
    )


class MysaClimate(MysaEntity, ClimateEntity):
    """One thermostat.

    Fan and swing live here rather than in selects of their own: Home Assistant's
    climate entity carries all three, and a second entity for the same control would be
    a second thing to keep in step with the first.
    """

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: MysaCoordinator, device: MysaDevice) -> None:
        super().__init__(coordinator, device)
        self._attr_supported_features = self._features()

    def _features(self) -> ClimateEntityFeature:
        """Set only where the control has something to offer (spec 09)."""
        features = ClimateEntityFeature(0)
        capabilities = self.device.capabilities
        if capabilities & {Capability.HEAT, Capability.COOL}:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        for capability, flag in (
            (Capability.FAN, ClimateEntityFeature.FAN_MODE),
            (Capability.VERTICAL_SWING, ClimateEntityFeature.SWING_MODE),
            (Capability.HORIZONTAL_SWING, ClimateEntityFeature.SWING_HORIZONTAL_MODE),
        ):
            if self.device.options(capability):
                features |= flag
        modes = self.hvac_modes
        if HVACMode.OFF in modes and len(modes) > 1:
            features |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        return features

    # Reading.

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return [HVAC_MODES[name] for name in self.device.modes if name in HVAC_MODES]

    @property
    def hvac_mode(self) -> HVACMode | None:
        """None where the device holds a mode value nothing names (spec 02)."""
        return HVAC_MODES.get(self.device.mode or "")

    @property
    def current_temperature(self) -> float | None:
        return self.device.current_temperature

    @property
    def current_humidity(self) -> float | None:
        return self.device.humidity

    @property
    def target_temperature(self) -> float | None:
        return self.device.target_temperature

    @property
    def target_temperature_step(self) -> float:
        return self.device.setpoint_step

    @property
    def min_temp(self) -> float:
        bounds = self.device.setpoint_range
        return bounds[0] if bounds else super().min_temp

    @property
    def max_temp(self) -> float:
        bounds = self.device.setpoint_range
        return bounds[1] if bounds else super().max_temp

    @property
    def fan_modes(self) -> list[str] | None:
        return list(self.device.options(Capability.FAN)) or None

    @property
    def fan_mode(self) -> str | None:
        return self.device.fan_speed

    @property
    def swing_modes(self) -> list[str] | None:
        return list(self.device.options(Capability.VERTICAL_SWING)) or None

    @property
    def swing_mode(self) -> str | None:
        return self.device.vertical_swing

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        return list(self.device.options(Capability.HORIZONTAL_SWING)) or None

    @property
    def swing_horizontal_mode(self) -> str | None:
        return self.device.horizontal_swing

    # Writing.

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.write(self.device.set_mode(MYSA_MODES[hvac_mode]))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write the setpoint the current mode selects (spec 03)."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.write(self.device.set_temperature(float(temperature)))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.write(self.device.set_fan_speed(fan_mode))

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        await self.write(self.device.set_vertical_swing(swing_mode))

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        await self.write(self.device.set_horizontal_swing(swing_horizontal_mode))
