"""Pool-logica: eigen aFRR-vlag publiceren, die van de anderen ontvangen."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from datetime import timedelta

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval

from .balans import BalansAuthError, BalansClient, BalansConnectionError
from .const import (
    BROKER_PORT,
    FLAG_TTL_SECONDS,
    HEARTBEAT_SECONDS,
    HISTORY_KEEP_SECONDS,
    HISTORY_SECONDS,
    STALE_OFFLINE_SECONDS,
    POLL_SECONDS,
    SIGNAL_UPDATE,
    TOPIC_PREFIX,
)

_LOGGER = logging.getLogger(__name__)


def clean_history(value) -> dict[int, str]:
    """Lijst [[start_s, 'e'/'i'/'ie'/''], ...] naar dict, alleen geldige en recente kwartieren."""
    out: dict[int, str] = {}
    if not isinstance(value, list):
        return out
    cutoff = time.time() - HISTORY_KEEP_SECONDS
    for item in value[:400]:
        if isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], (int, float)) and isinstance(item[1], str):
            start = int(item[0]) // 900 * 900
            if start >= cutoff:
                out[start] = "".join(c for c in ("i", "e") if c in item[1])
    return out


def clean_soc(value) -> dict[int, int]:
    out: dict[int, int] = {}
    if not isinstance(value, list):
        return out
    cutoff = time.time() - HISTORY_KEEP_SECONDS
    for item in value[:400]:
        if isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], (int, float)) and isinstance(item[1], (int, float)):
            start = int(item[0]) // 900 * 900
            if start >= cutoff and 0 <= item[1] <= 100:
                out[start] = int(round(item[1]))
    return out


def dir_letters(direction: str) -> str:
    return {"export": "e", "import": "i"}.get(direction, "")


def own_direction(flag: dict) -> str:
    if flag.get("af") != 1:
        return ""
    ad = flag.get("ad") or ""
    if ad == "e":
        return "export"
    if ad == "i":
        return "import"
    return "afrr"


class PoolHub:
    """Eén per config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str, host: str, name: str, code: str, balans: BalansClient) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.host = host
        self.name = name
        self._code = code
        self.balans = balans
        self.members: dict[str, dict] = {}
        self.own: str = ""
        self.balans_status = "verbinden"
        self.broker_status = "verbinden"
        self._last_sent: str | None = None
        self._last_sent_t = 0.0
        self._client: mqtt.Client | None = None
        self._unsub = None
        self._unsub_hist = None
        self.log: dict[int, str] = {}
        self.soc_entity: str | None = None
        self.soc_now: int | None = None
        self.soc_log: dict[int, int] = {}
        self._log_sent: tuple | None = None
        self._soc_sent: int | None = None

    # ---------- MQTT (draait in de paho-thread; alles terug naar de event loop) ----------
    def _make_client(self) -> mqtt.Client:
        client_id = f"pool-{self.name}-{int(time.time())}"
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        except AttributeError:
            client = mqtt.Client(client_id=client_id)
        client.username_pw_set(self.name, self._code)
        client.tls_set_context(ssl.create_default_context())
        client.will_set(
            TOPIC_PREFIX + self.name,
            json.dumps({"n": self.name, "r": "", "on": False, "t": int(time.time()), "offline": True}),
            qos=1,
            retain=True,
        )
        client.reconnect_delay_set(min_delay=2, max_delay=30)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        return client

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        code = rc if isinstance(rc, int) else getattr(rc, "value", 0)
        if code == 0:
            client.subscribe(TOPIC_PREFIX + "+", qos=1)
            self.hass.loop.call_soon_threadsafe(self._set_broker, "verbonden")
        else:
            self.hass.loop.call_soon_threadsafe(self._set_broker, f"geweigerd ({rc})")

    def _on_disconnect(self, client, userdata, *args):
        self.hass.loop.call_soon_threadsafe(self._set_broker, "verbinden")

    def _on_message(self, client, userdata, msg):
        topic_name = msg.topic.split("/")[-1][:24]
        if not msg.payload:  # vastgehouden bericht gewist: lid weg
            self.hass.loop.call_soon_threadsafe(self._drop_member, topic_name)
            return
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(data, dict):
            return
        name = str(data.get("n") or topic_name)[:24]
        if not name:
            return
        stamp = float(data.get("t") or 0)
        if not data.get("on") and not data.get("h") and time.time() - stamp > STALE_OFFLINE_SECONDS:
            return  # oud offline-bericht zonder geschiedenis (bijv. een testnaam): negeren
        record = {
            "r": data.get("r") if data.get("r") in ("export", "import", "afrr") else "",
            "on": bool(data.get("on")),
            "t": float(data.get("t") or 0),
            "rx": time.time(),
            "h": clean_history(data.get("h")) if "h" in data else None,
            "soc": int(data["soc"]) if isinstance(data.get("soc"), (int, float)) and 0 <= data["soc"] <= 100 else None,
            "hs": clean_soc(data.get("hs")) if "hs" in data else None,
        }
        self.hass.loop.call_soon_threadsafe(self._set_member, name, record)

    @callback
    def _set_broker(self, status: str) -> None:
        self.broker_status = status
        if status == "verbonden":
            self._last_sent = None  # na (her)verbinden eigen status opnieuw sturen
            self._log_sent = None
        self._notify()

    @callback
    def _drop_member(self, name: str) -> None:
        if self.members.pop(name, None) is not None:
            self._notify()

    @callback
    def _set_member(self, name: str, record: dict) -> None:
        old = self.members.get(name) or {}
        if record["h"] is None:  # bericht zonder geschiedenis (bijv. offline-melding): vorige houden
            record["h"] = old.get("h") or {}
        if record["hs"] is None:
            record["hs"] = old.get("hs") or {}
        self.members[name] = record
        self._notify()

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(self.entry_id))

    # ---------- levenscyclus ----------
    async def async_start(self) -> None:
        self._client = await self.hass.async_add_executor_job(self._make_client)
        await self.hass.async_add_executor_job(self._client.connect_async, self.host, BROKER_PORT, 30)
        self._client.loop_start()
        self._unsub = async_track_time_interval(self.hass, self._tick, timedelta(seconds=POLL_SECONDS))
        self._unsub_hist = async_track_time_interval(self.hass, self._history, timedelta(seconds=HISTORY_SECONDS))
        self.hass.async_create_task(self._history())
        self.hass.async_create_task(self._tick())

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._unsub_hist:
            self._unsub_hist()
            self._unsub_hist = None
        if self._client is not None:
            client = self._client
            self._client = None
            await self.hass.async_add_executor_job(self._shutdown_client, client)
        await self.balans.close()

    def _shutdown_client(self, client: mqtt.Client) -> None:
        try:
            client.publish(TOPIC_PREFIX + self.name, json.dumps({"n": self.name, "r": "", "on": False, "t": int(time.time()), "h": self.history_list()}), qos=1, retain=True)
            client.loop_stop()
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def soc_list(self) -> list[list]:
        cutoff = time.time() - HISTORY_KEEP_SECONDS
        return [[start, self.soc_log[start]] for start in sorted(self.soc_log) if start >= cutoff]

    def _read_soc(self, now: float) -> None:
        st = self.hass.states.get(self.soc_entity) if self.soc_entity else None
        try:
            value = float(st.state) if st else None
        except ValueError:
            value = None
        if value is None or not 0 <= value <= 100:
            self.soc_now = None
            return
        self.soc_now = int(round(value))
        self.soc_log[int(now) // 900 * 900] = self.soc_now  # laatste waarde = SOC aan het kwartiereinde
        cutoff = now - HISTORY_KEEP_SECONDS
        for key in [k for k in self.soc_log if k < cutoff]:
            del self.soc_log[key]

    def history_list(self) -> list[list]:
        cutoff = time.time() - HISTORY_KEEP_SECONDS
        return [[start, self.log[start]] for start in sorted(self.log) if start >= cutoff]

    async def _history(self, _now=None) -> None:
        """Eigen aFRR-kwartieren van de afgelopen ~26 uur bij Balans ophalen (met terugwerkende kracht)."""
        try:
            rows = await self.balans.history()
        except (BalansAuthError, BalansConnectionError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Geschiedenis niet opgehaald: %s", err)
            return
        for start, letters in rows:
            if letters or start not in self.log:
                self.log[start] = letters
        cutoff = time.time() - HISTORY_KEEP_SECONDS
        self.log = {k: v for k, v in self.log.items() if k >= cutoff}
        self._notify()

    async def _tick(self, _now=None) -> None:
        try:
            flag = await self.balans.current_flag()
            self.own = own_direction(flag)
            self.balans_status = "ingelogd"
        except BalansAuthError:
            self.balans_status = "login geweigerd"
            self._notify()
            return
        except (BalansConnectionError, asyncio.TimeoutError) as err:
            self.balans_status = "niet bereikbaar"
            _LOGGER.debug("Balans niet bereikbaar: %s", err)
            self._notify()
            return
        now = time.time()
        self._read_soc(now)
        if self.own:
            self.log[int(now) // 900 * 900] = dir_letters(self.own) or self.log.get(int(now) // 900 * 900, "")
        if self._client is not None and self.broker_status == "verbonden":
            history = self.history_list()
            socs = self.soc_list()
            changed = self.own != self._last_sent or tuple(map(tuple, history)) != self._log_sent or self.soc_now != self._soc_sent
            beat = self.own != "" and now - self._last_sent_t >= HEARTBEAT_SECONDS
            if changed or beat:
                payload = {"n": self.name, "r": self.own, "on": self.own != "", "q": (int(now) // 900) * 900, "t": int(now), "h": history,
                           "soc": self.soc_now, "hs": socs}
                info = self._client.publish(TOPIC_PREFIX + self.name, json.dumps(payload, separators=(",", ":")), qos=1, retain=True)
                if info.rc == 0:
                    self._last_sent = self.own
                    self._last_sent_t = now
                    self._log_sent = tuple(map(tuple, history))
                    self._soc_sent = self.soc_now
        self._notify()

    # ---------- afgeleide toestand ----------
    def direction_of(self, name: str) -> str:
        member = self.members.get(name)
        if not member or not member["on"]:
            return ""
        if time.time() - max(member["t"], member["rx"] - 5) > FLAG_TTL_SECONDS:
            return ""
        return member["r"]

    def soc_of(self, name: str):
        member = self.members.get(name) or {}
        log = member.get("hs") or {}
        return member.get("soc"), [[start, log[start]] for start in sorted(log)]

    def history_of(self, name: str) -> list[list]:
        member = self.members.get(name) or {}
        log = member.get("h") or {}
        return [[start, log[start]] for start in sorted(log)]

    def others(self, direction: str) -> list[str]:
        return sorted(n for n in self.members if n != self.name and self.direction_of(n) == direction)
