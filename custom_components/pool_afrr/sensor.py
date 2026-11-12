"""Sensoren voor Pool aFRR."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_UPDATE
from .pool import PoolHub

OPTIONS = ["export", "import", "beide", "geen"]
MEMBER_OPTIONS = ["export", "import", "afrr", "geen"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub: PoolHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PoolTotal(hub, entry), PoolOwn(hub, entry), PoolStatus(hub, entry)])
    known: set[str] = set()

    @callback
    def add_members() -> None:
        new = [name for name in hub.members if name != hub.name and name not in known]
        if new:
            known.update(new)
            async_add_entities([PoolMember(hub, entry, name) for name in new])

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATE.format(entry.entry_id), add_members))


def history_attrs(rows: list[list], soc=None, socs=None, ends=None, energy=None, starts=None) -> dict:
    """kwartieren: [[start_s, 'e'/'i'/'ie'/''], ...] van de afgelopen 48 uur; plus tellers voor de laatste 24 uur."""
    import time

    day = time.time() - 86400
    recent = [row for row in rows if row[0] >= day]
    return {
        "kwartieren": rows,
        "export_24u": sum(1 for row in recent if "e" in row[1]),
        "import_24u": sum(1 for row in recent if "i" in row[1]),
        "afrr_24u": len(recent),
        "soc": soc,
        "soc_kwartieren": socs or [],  # SOC bij de start van het kwartier
        "soc_kwartier_eind": ends or [],  # SOC aan het eind van het kwartier
        "energie_kwartieren": energy or [],  # [[start, export_kWh, import_kWh]] netto volgens het BE-dashboard
        "vlag_start": starts or [],  # [[start, sec tot export-vlag, sec tot import-vlag]] (None = onbekend)
    }


class PoolEntity(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: PoolHub, entry: ConfigEntry, key: str) -> None:
        self.hub = hub
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="Pool aFRR", manufacturer="Pool aFRR")

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE.format(self.hub.entry_id), self.async_write_ha_state))


class PoolTotal(PoolEntity):
    _attr_translation_key = "pool"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = OPTIONS
    _attr_icon = "mdi:account-group"

    def __init__(self, hub, entry):
        super().__init__(hub, entry, "pool")

    @property
    def native_value(self):
        exp, imp = self.hub.others("export"), self.hub.others("import")
        return "beide" if exp and imp else "export" if exp else "import" if imp else "geen"

    @property
    def extra_state_attributes(self):
        exp, imp = self.hub.others("export"), self.hub.others("import")
        return {"export_namen": exp, "import_namen": imp, "export_aantal": len(exp), "import_aantal": len(imp)}


class PoolOwn(PoolEntity):
    _attr_translation_key = "own"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = MEMBER_OPTIONS
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, hub, entry):
        super().__init__(hub, entry, "own")

    _unrecorded_attributes = frozenset({"kwartieren", "soc_kwartieren", "soc_kwartier_eind", "energie_kwartieren", "vlag_start"})

    @property
    def native_value(self):
        return self.hub.own or "geen"

    @property
    def extra_state_attributes(self):
        return {**history_attrs(self.hub.history_list(), self.hub.soc_now, self.hub.soc_list(), self.hub.soc_list(self.hub.soc_end), self.hub.energy_list(), self.hub.start_list()), "gebied": self.hub.area}


class PoolStatus(PoolEntity):
    _attr_translation_key = "status"
    _attr_icon = "mdi:lan-connect"

    def __init__(self, hub, entry):
        super().__init__(hub, entry, "status")

    @property
    def native_value(self):
        return self.hub.broker_status

    @property
    def extra_state_attributes(self):
        return {"balans": self.hub.balans_status, "naam": self.hub.name}


class PoolMember(PoolEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = MEMBER_OPTIONS

    def __init__(self, hub, entry, name):
        super().__init__(hub, entry, f"member_{name.lower()}")
        self._member = name
        self._attr_name = name

    _unrecorded_attributes = frozenset({"kwartieren", "soc_kwartieren", "soc_kwartier_eind", "energie_kwartieren", "vlag_start"})

    @property
    def native_value(self):
        return self.hub.direction_of(self._member) or "geen"

    @property
    def extra_state_attributes(self):
        soc, socs, ends = self.hub.soc_of(self._member)
        energy, starts = self.hub.extra_of(self._member)
        return {**history_attrs(self.hub.history_of(self._member), soc, socs, ends, energy, starts), "gebied": self.hub.area_of(self._member)}

    @property
    def icon(self):
        value = self.native_value
        return "mdi:transmission-tower-export" if value == "export" else "mdi:transmission-tower-import" if value == "import" else "mdi:transmission-tower"
