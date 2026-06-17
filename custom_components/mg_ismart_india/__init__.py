"""MG iSmart India integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .client import MgIndiaClient
from .const import (
    CONF_PASSWORD,
    CONF_PHONE,
    CONF_PIN_HASH,
    CONF_VIN,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MgIndiaDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MG iSmart India from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    client = MgIndiaClient(
        entry.data[CONF_PHONE],
        entry.data[CONF_PASSWORD],
        vin=entry.data.get(CONF_VIN),
        pin_hash=entry.options.get(CONF_PIN_HASH),
    )
    coordinator = MgIndiaDataUpdateCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an MG iSmart India config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].close()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when its options change."""

    await hass.config_entries.async_reload(entry.entry_id)
