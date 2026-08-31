"""What every Mysa entity has in common. See docs/specs/06-ha-entities.md."""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pymysa import MysaDevice, MysaError, UnsupportedCommand, ValueRefused

from .const import DOMAIN, MANUFACTURER
from .coordinator import MysaCoordinator


class MysaEntity(CoordinatorEntity[MysaCoordinator]):
    """One entity on one device.

    The device object is a live view of the account's cache and keeps its identity
    across refreshes (spec 09), so an entity holds it rather than looking it up.
    """

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: MysaCoordinator, device: MysaDevice, key: str | None = None
    ) -> None:
        super().__init__(coordinator)
        self.device = device
        # Fixed: Home Assistant matches on unique_id, and changing the scheme later
        # would strand every entity a user already has.
        self._attr_unique_id = device.id if key is None else f"{device.id}-{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.id)},
            manufacturer=MANUFACTURER,
            model=device.model or None,
            name=device.name,
            serial_number=device.serial,
            sw_version=device.firmware,
        )

    @property
    def available(self) -> bool:
        return super().available and self.device.available

    async def write(self, action: Coroutine[Any, Any, None]) -> None:
        """Perform a write and show its result.

        The setter returns once the backend accepts it, with the written value already
        readable from the device (spec 09), so the state is written straight away and
        the refresh replaces it with what the next poll reports.
        """
        try:
            await action
        except ValueRefused as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="write_refused",
                translation_placeholders={"device": self.device.name, "reason": str(err)},
            ) from err
        except UnsupportedCommand as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="write_unsupported",
                translation_placeholders={"device": self.device.name, "reason": str(err)},
            ) from err
        except MysaError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"device": self.device.name, "reason": str(err)},
            ) from err
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
