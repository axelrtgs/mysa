"""Releasing a schedule hold. See docs/specs/06-ha-entities.md and spec 08."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pymysa import MysaDevice

from .const import DOMAIN
from .coordinator import MysaConfigEntry, MysaCoordinator
from .entity import MysaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MysaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MysaReleaseHold(coordinator, device)
        for device in coordinator.account.devices.values()
        if device.schedule is not None
    )


class MysaReleaseHold(MysaEntity, ButtonEntity):
    """Ends a hold and follows the schedule again.

    A button and not a switch: writing `holding: false` ends a hold, and nothing
    observed starts one, because whatever creates a hold carries the setting being held
    and the state document does not (spec 08).
    """

    _attr_translation_key = "release_hold"

    def __init__(self, coordinator: MysaCoordinator, device: MysaDevice) -> None:
        super().__init__(coordinator, device, "release_hold")

    @property
    def available(self) -> bool:
        """Deleting the schedule removes the section, and with it the hold."""
        return super().available and self.device.schedule is not None

    async def async_press(self) -> None:
        hold = self.device.schedule
        if hold is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="no_schedule",
                translation_placeholders={"device": self.device.name},
            )
        await self.write(hold.release())
