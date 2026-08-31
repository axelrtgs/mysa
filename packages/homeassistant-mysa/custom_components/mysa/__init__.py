"""The Mysa integration. See docs/specs/06-ha-entities.md."""

from __future__ import annotations

from homeassistant.const import CONF_SCAN_INTERVAL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pymysa import MysaAuth

from .const import CONF_HOMES, CONF_REFRESH_TOKEN, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import MysaConfigEntry, MysaCoordinator

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: MysaConfigEntry) -> bool:
    """Restore the session, discover what the entry includes, and start polling."""
    session = async_get_clientsession(hass)
    auth = MysaAuth.from_refresh_token(
        entry.data[CONF_USERNAME], entry.data[CONF_REFRESH_TOKEN], session
    )
    homes = entry.options.get(CONF_HOMES)
    coordinator = MysaCoordinator(
        hass,
        entry,
        auth,
        session,
        list(homes) if homes else None,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    coordinator.report_missing()

    entry.runtime_data = coordinator
    _forget_removed(hass, entry, set(coordinator.account.devices))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MysaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.account.aclose()
    return unloaded


def _forget_removed(
    hass: HomeAssistant, entry: MysaConfigEntry, discovered: set[str]
) -> None:
    """Drop devices discovery no longer returns, which takes their entities with them.

    A home removed from the entry, or a device removed from the account, otherwise
    leaves an unavailable thermostat behind for good.
    """
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if not any(
            domain == DOMAIN and identifier in discovered
            for domain, identifier in device.identifiers
        ):
            registry.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )


async def _reload(hass: HomeAssistant, entry: MysaConfigEntry) -> None:
    """Rerun discovery, so a home added or removed adds or removes its devices."""
    await hass.config_entries.async_reload(entry.entry_id)
