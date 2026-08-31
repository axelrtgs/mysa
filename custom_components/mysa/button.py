"""Releasing a schedule hold. See docs/specs/06-ha-entities.md and spec 08."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pymysa import MysaDevice

from .const import DOMAIN
from .coordinator import MysaConfigEntry, MysaCoordinator
from .entity import MysaEntity


def holding(device: MysaDevice) -> bool:
    """Whether there is a hold to release."""
    hold = device.schedule
    return hold is not None and hold.holding is True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MysaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Follow the holds, which come and go without the entry reloading.

    A button's state is the timestamp of its last press, so there is no history to keep
    by leaving it in place unavailable - and a button that cannot do anything is worse
    than no button (spec 06).
    """
    coordinator = entry.runtime_data
    live: dict[str, MysaReleaseHold] = {}

    async def forget(entity: MysaReleaseHold) -> None:
        await entity.async_remove(force_remove=True)
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(Platform.BUTTON, DOMAIN, entity.unique_id or "")
        if entity_id:
            registry.async_remove(entity_id)

    @callback
    def follow() -> None:
        for device in coordinator.account.devices.values():
            if holding(device) and device.id not in live:
                live[device.id] = MysaReleaseHold(coordinator, device)
                async_add_entities([live[device.id]])
            elif not holding(device) and device.id in live:
                entry.async_create_task(hass, forget(live.pop(device.id)))

    follow()
    entry.async_on_unload(coordinator.async_add_listener(follow))


class MysaReleaseHold(MysaEntity, ButtonEntity):
    """Ends a hold and follows the schedule again.

    A button and not a switch: writing `holding: false` ends a hold, and nothing observed
    starts one, because whatever creates a hold carries the setting being held and the
    state document does not (spec 08).
    """

    _attr_translation_key = "release_hold"

    def __init__(self, coordinator: MysaCoordinator, device: MysaDevice) -> None:
        super().__init__(coordinator, device, "release_hold")

    async def async_press(self) -> None:
        hold = self.device.schedule
        if hold is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="no_schedule",
                translation_placeholders={"device": self.device.name},
            )
        await self.write(hold.release())
