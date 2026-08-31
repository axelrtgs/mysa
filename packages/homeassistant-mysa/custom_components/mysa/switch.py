"""Settings that are on or off. See docs/specs/06-ha-entities.md."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pymysa import Capability, MysaDevice

from .coordinator import MysaConfigEntry, MysaCoordinator
from .entity import MysaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MysaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MysaProximity(coordinator, device)
        for device in coordinator.account.devices.values()
        if device.supports(Capability.PROXIMITY)
    )


class MysaProximity(MysaEntity, SwitchEntity):
    """Whether the display wakes when someone approaches.

    A BB-V1-0 reports the field and declares it read-only, so it has no switch: a field
    being readable is not a control (spec 02).
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "proximity"

    def __init__(self, coordinator: MysaCoordinator, device: MysaDevice) -> None:
        super().__init__(coordinator, device, "proximity")

    @property
    def is_on(self) -> bool | None:
        return self.device.proximity

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.write(self.device.set_proximity(True))

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.write(self.device.set_proximity(False))
