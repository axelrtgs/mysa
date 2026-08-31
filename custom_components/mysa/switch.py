"""Settings that are on or off. See docs/specs/06-ha-entities.md."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pymysa import Capability, MysaDevice

from .coordinator import MysaConfigEntry, MysaCoordinator
from .entity import MysaEntity


@dataclass(frozen=True, kw_only=True)
class MysaSwitchDescription(SwitchEntityDescription):
    """A setting, the capability that declares it, and how to move it."""

    capability: Capability
    value_fn: Callable[[MysaDevice], bool | None]
    set_fn: Callable[[MysaDevice, bool], Coroutine[Any, Any, None]]


SWITCHES: tuple[MysaSwitchDescription, ...] = (
    # A BB-V1-0 reports `wakeOnApproach` and declares it read-only, so it has no switch.
    MysaSwitchDescription(
        key="proximity",
        translation_key="proximity",
        entity_category=EntityCategory.CONFIG,
        capability=Capability.PROXIMITY,
        value_fn=lambda device: device.proximity,
        set_fn=lambda device, on: device.set_proximity(on),
    ),
    # None where the device holds one of the two intensity modes nothing names (spec 02).
    MysaSwitchDescription(
        key="adaptive_brightness",
        translation_key="adaptive_brightness",
        entity_category=EntityCategory.CONFIG,
        capability=Capability.ADAPTIVE_BRIGHTNESS,
        value_fn=lambda device: (
            None if device.brightness_mode is None else device.brightness_mode == "adaptive"
        ),
        set_fn=lambda device, on: device.set_adaptive_brightness(on),
    ),
    # A BB-V1-0 holds it on the device record, which has no write path (spec 02), so
    # that model reports it as a binary sensor instead.
    MysaSwitchDescription(
        key="early_on",
        translation_key="early_on",
        entity_category=EntityCategory.CONFIG,
        capability=Capability.EARLY_ON,
        value_fn=lambda device: device.early_on,
        set_fn=lambda device, on: device.set_early_on(on),
    ),
    MysaSwitchDescription(
        key="thermostatic",
        translation_key="thermostatic",
        entity_category=EntityCategory.CONFIG,
        capability=Capability.THERMOSTATIC,
        value_fn=lambda device: device.thermostatic,
        set_fn=lambda device, on: device.set_thermostatic(on),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MysaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MysaSwitch(coordinator, device, description)
        for device in coordinator.account.devices.values()
        for description in SWITCHES
        if device.supports(description.capability)
    )


class MysaSwitch(MysaEntity, SwitchEntity):
    """One setting that is on or off."""

    entity_description: MysaSwitchDescription

    def __init__(
        self,
        coordinator: MysaCoordinator,
        device: MysaDevice,
        description: MysaSwitchDescription,
    ) -> None:
        super().__init__(coordinator, device, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.device)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.write(self.entity_description.set_fn(self.device, True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.write(self.entity_description.set_fn(self.device, False))
