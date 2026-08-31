"""Connectivity, and whether the backend has firmware for the device.

See docs/specs/06-ha-entities.md.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pymysa import MysaDevice

from .coordinator import MysaConfigEntry, MysaCoordinator
from .entity import MysaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MysaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[MysaEntity] = []
    for device in coordinator.account.devices.values():
        entities.append(MysaConnectivity(coordinator, device))
        if device.firmware_update is not None:
            entities.append(MysaFirmware(coordinator, device))
    async_add_entities(entities)


class MysaConnectivity(MysaEntity, BinarySensorEntity):
    """Whether the device reports itself connected."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "connected"

    def __init__(self, coordinator: MysaCoordinator, device: MysaDevice) -> None:
        super().__init__(coordinator, device, "connected")

    @property
    def available(self) -> bool:
        """Available while the poll works, connected or not.

        The entity whose job is to say the device is offline cannot go unavailable for
        being offline.
        """
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        return self.device.available


class MysaFirmware(MysaEntity, BinarySensorEntity):
    """Whether the backend would give this device a newer firmware.

    It reports and does not install: no install path has been observed on any surface
    this project reads (spec 06).
    """

    _attr_device_class = BinarySensorDeviceClass.UPDATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "firmware_update"

    def __init__(self, coordinator: MysaCoordinator, device: MysaDevice) -> None:
        super().__init__(coordinator, device, "firmware_update")

    @property
    def is_on(self) -> bool | None:
        update = self.device.firmware_update
        return update.available if update else None

    @property
    def extra_state_attributes(self) -> dict[str, str | None] | None:
        update = self.device.firmware_update
        if update is None:
            return None
        return {"installed_version": update.installed, "latest_version": update.allowed}
