"""Named settings with more than one value. See docs/specs/06-ha-entities.md."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pymysa import Capability, MysaDevice

from .coordinator import MysaConfigEntry, MysaCoordinator
from .entity import MysaEntity


@dataclass(frozen=True, kw_only=True)
class MysaSelectDescription(SelectEntityDescription):
    """A control, the capability that declares it, and how to move it."""

    capability: Capability
    value_fn: Callable[[MysaDevice], str | None]
    set_fn: Callable[[MysaDevice, str], Coroutine[Any, Any, None]]


SELECTS: tuple[MysaSelectDescription, ...] = (
    # Three values on a BB-V3-0 - unlocked, limited to the lockout range, full - which
    # is why this is not a switch (spec 02).
    MysaSelectDescription(
        key="lock",
        translation_key="lock",
        entity_category=EntityCategory.CONFIG,
        capability=Capability.LOCK,
        value_fn=lambda device: device.lock,
        set_fn=lambda device, option: device.set_lock(option),
    ),
    # The values differ by model: a BB-V1-0's 4 is radiant and a BB-V3-0 has no 4.
    MysaSelectDescription(
        key="heater_type",
        translation_key="heater_type",
        entity_category=EntityCategory.CONFIG,
        capability=Capability.HEATER_TYPE,
        value_fn=lambda device: device.heater_type,
        set_fn=lambda device, option: device.set_heater_type(option),
    ),
    MysaSelectDescription(
        key="temperature_format",
        translation_key="temperature_format",
        entity_category=EntityCategory.CONFIG,
        capability=Capability.TEMPERATURE_FORMAT,
        value_fn=lambda device: device.temperature_format,
        set_fn=lambda device, option: device.set_temperature_format(option),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MysaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MysaSelect(coordinator, device, description)
        for device in coordinator.account.devices.values()
        for description in SELECTS
        # An empty option list is a control with nothing to choose (spec 09).
        if len(device.options(description.capability)) > 1
    )


class MysaSelect(MysaEntity, SelectEntity):
    """One named setting."""

    entity_description: MysaSelectDescription

    def __init__(
        self,
        coordinator: MysaCoordinator,
        device: MysaDevice,
        description: MysaSelectDescription,
    ) -> None:
        super().__init__(coordinator, device, description.key)
        self.entity_description = description
        self._attr_options = list(device.options(description.capability))

    @property
    def current_option(self) -> str | None:
        """None where the device holds a value nothing names (spec 02)."""
        return self.entity_description.value_fn(self.device)

    async def async_select_option(self, option: str) -> None:
        await self.write(self.entity_description.set_fn(self.device, option))
