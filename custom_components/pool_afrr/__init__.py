"""Pool aFRR: deel aFRR-activaties binnen een groep Balans Energie-gebruikers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .balans import BalansClient
from .const import CONF_BE_PASSWORD, CONF_BE_USERNAME, CONF_HOST, CONF_NAME, CONF_POOL_CODE, CONF_SOC, DOMAIN
from .pool import PoolHub

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    balans = BalansClient(entry.data[CONF_BE_USERNAME], entry.data[CONF_BE_PASSWORD])
    hub = PoolHub(hass, entry.entry_id, entry.data[CONF_HOST], entry.data[CONF_NAME], entry.data[CONF_POOL_CODE], balans)
    hub.soc_entity = entry.options.get(CONF_SOC) or entry.data.get(CONF_SOC)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub
    await hub.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hub: PoolHub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.async_stop()
    return unloaded
