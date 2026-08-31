"""Measurements. See docs/specs/06-ha-entities.md."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from pymysa import Home, MysaDevice

from .coordinator import MysaConfigEntry, MysaCoordinator
from .entity import MysaEntity

type Reading = StateType | datetime


@dataclass(frozen=True, kw_only=True)
class MysaSensorDescription(SensorEntityDescription):
    """A measurement and where it is read from."""

    value_fn: Callable[[MysaDevice, Home | None], Reading]
    #: Whether the device has this at all. Defaults to reporting a value (spec 06).
    exists_fn: Callable[[MysaDevice, Home | None], bool] | None = None
    #: Whether it still has it. Defaults to existing being enough.
    available_fn: Callable[[MysaDevice], bool] | None = None


def _next_event(device: MysaDevice) -> datetime | None:
    hold = device.schedule
    return hold.next_event if hold else None


SENSORS: tuple[MysaSensorDescription, ...] = (
    MysaSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device, _: device.current_temperature,
    ),
    MysaSensorDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device, _: device.humidity,
    ),
    # Milliamps: 12458 with 240 V and 2989 W is consistent at no other scale (spec 02).
    MysaSensorDescription(
        key="current",
        translation_key="current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device, _: device.current,
    ),
    MysaSensorDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device, _: device.voltage,
    ),
    MysaSensorDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device, _: device.wattage,
    ),
    # Kilowatt hours on evidence that does not exist yet (spec 05).
    MysaSensorDescription(
        key="energy",
        translation_key="energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device, _: device.energy,
    ),
    # No unit: nothing establishes one, and nothing downstream needs it (spec 05).
    MysaSensorDescription(
        key="power_consumed",
        translation_key="power_consumed",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device, _: device.power_consumed,
    ),
    MysaSensorDescription(
        key="duty_cycle",
        translation_key="duty_cycle",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device, _: device.duty_cycle,
    ),
    MysaSensorDescription(
        key="signal_strength",
        translation_key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device, _: device.signal_strength,
    ),
    # The payload names no currency (spec 02), so neither does the entity.
    MysaSensorDescription(
        key="electricity_rate",
        translation_key="electricity_rate",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _, home: home.electricity_rate if home else None,
    ),
    MysaSensorDescription(
        key="schedule_next_event",
        translation_key="schedule_next_event",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device, _: _next_event(device),
        # A hold with no end reports no timestamp and is still a hold (spec 08).
        exists_fn=lambda device, _: device.schedule is not None,
        available_fn=lambda device: device.schedule is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MysaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MysaSensor(coordinator, device, description)
        for device in coordinator.account.devices.values()
        for description in SENSORS
        if _exists(description, device, coordinator.account.home_of(device))
    )


def _exists(
    description: MysaSensorDescription, device: MysaDevice, home: Home | None
) -> bool:
    if description.exists_fn is not None:
        return description.exists_fn(device, home)
    return description.value_fn(device, home) is not None


class MysaSensor(MysaEntity, SensorEntity):
    """One reading."""

    entity_description: MysaSensorDescription

    def __init__(
        self,
        coordinator: MysaCoordinator,
        device: MysaDevice,
        description: MysaSensorDescription,
    ) -> None:
        super().__init__(coordinator, device, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        follows = self.entity_description.available_fn
        return super().available and (follows is None or follows(self.device))

    @property
    def native_value(self) -> Reading:
        home = self.coordinator.account.home_of(self.device)
        return self.entity_description.value_fn(self.device, home)
