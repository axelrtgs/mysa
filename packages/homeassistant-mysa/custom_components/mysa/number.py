"""Settings held as a number. See docs/specs/06-ha-entities.md."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pymysa import Capability, MysaDevice

from .const import DOMAIN
from .coordinator import MysaConfigEntry, MysaCoordinator
from .entity import MysaEntity

#: Where the device declares no range of its own, the display's own scale.
BRIGHTNESS_RANGE = (0.0, 100.0)


@dataclass(frozen=True, kw_only=True)
class MysaNumberDescription(NumberEntityDescription):
    """A setting, the capability that declares it, and how to move it."""

    capability: Capability
    value_fn: Callable[[MysaDevice], float | None]
    set_fn: Callable[[MysaDevice, float], Coroutine[Any, Any, None]]
    #: Bounds from the device, where it declares any.
    range_fn: Callable[[MysaDevice], tuple[float, float] | None] = (
        lambda _: BRIGHTNESS_RANGE
    )


def _limits(device: MysaDevice) -> tuple[float, float]:
    """The lockout pair as it stands, for the half that is not being written."""
    low, high = device.min_setpoint, device.max_setpoint
    if low is None or high is None:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="no_setpoint_limits",
            translation_placeholders={"device": device.name},
        )
    return low, high


async def _set_min(device: MysaDevice, value: float) -> None:
    await device.set_setpoint_limits(value, _limits(device)[1])


async def _set_max(device: MysaDevice, value: float) -> None:
    await device.set_setpoint_limits(_limits(device)[0], value)


NUMBERS: tuple[MysaNumberDescription, ...] = (
    MysaNumberDescription(
        key="active_brightness",
        translation_key="active_brightness",
        native_unit_of_measurement=PERCENTAGE,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        capability=Capability.BRIGHTNESS,
        value_fn=lambda device: device.active_brightness,
        set_fn=lambda device, value: device.set_brightness(active=int(value)),
    ),
    MysaNumberDescription(
        key="idle_brightness",
        translation_key="idle_brightness",
        native_unit_of_measurement=PERCENTAGE,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        capability=Capability.BRIGHTNESS,
        value_fn=lambda device: device.idle_brightness,
        set_fn=lambda device, value: device.set_brightness(idle=int(value)),
    ),
    # Bounded by what the device declares, not by the limit being replaced: a lockout
    # that bounded itself could only ever be narrowed.
    MysaNumberDescription(
        key="min_setpoint",
        translation_key="min_setpoint",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        capability=Capability.SETPOINT_LIMITS,
        value_fn=lambda device: device.min_setpoint,
        set_fn=_set_min,
        range_fn=lambda device: device.declared_setpoint_range,
    ),
    MysaNumberDescription(
        key="max_setpoint",
        translation_key="max_setpoint",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        capability=Capability.SETPOINT_LIMITS,
        value_fn=lambda device: device.max_setpoint,
        set_fn=_set_max,
        range_fn=lambda device: device.declared_setpoint_range,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MysaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MysaNumber(coordinator, device, description)
        for device in coordinator.account.devices.values()
        for description in NUMBERS
        if device.supports(description.capability)
        and description.value_fn(device) is not None
    )


class MysaNumber(MysaEntity, NumberEntity):
    """One numeric setting."""

    entity_description: MysaNumberDescription

    def __init__(
        self,
        coordinator: MysaCoordinator,
        device: MysaDevice,
        description: MysaNumberDescription,
    ) -> None:
        super().__init__(coordinator, device, description.key)
        self.entity_description = description
        bounds = description.range_fn(device)
        if bounds is not None:
            self._attr_native_min_value, self._attr_native_max_value = bounds

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.device)

    async def async_set_native_value(self, value: float) -> None:
        await self.write(self.entity_description.set_fn(self.device, value))
