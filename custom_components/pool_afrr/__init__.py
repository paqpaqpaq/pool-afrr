"""Pool aFRR: deel aFRR-activaties binnen een groep Balans Energie-gebruikers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .balans import BalansClient
from .const import CONF_BE_PASSWORD, CONF_BE_USERNAME, CONF_HOST, CONF_NAME, CONF_POOL_CODE, DOMAIN
from .pool import PoolHub

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    balans = BalansClient(entry.data[CONF_BE_USERNAME], entry.data[CONF_BE_PASSWORD])
    hub = PoolHub(hass, entry.entry_id, entry.data[CONF_HOST], entry.data[CONF_NAME], entry.data[CONF_POOL_CODE], balans)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub
    await hub.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hub: PoolHub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.async_stop()
    return unloaded
