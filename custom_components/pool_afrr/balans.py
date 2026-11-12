"""Minimale Balans Energie-client: inloggen en de aFRR-status van het lopende kwartier lezen."""

from __future__ import annotations

import json
import re
import time

import aiohttp

from .const import BALANS_BASE

QUARTER_MS = 900_000
HISTORY_HOURS = 26
UA = "Mozilla/5.0 (HomeAssistant pool-aFRR)"


class BalansAuthError(Exception):
    """Inloggegevens geweigerd of sessie verlopen."""


class BalansConnectionError(Exception):
    """Balans niet bereikbaar."""


class BalansClient:
    """Houdt een eigen cookie-jar bij; het wachtwoord blijft in de config entry."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._installation: str | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(),
                headers={"User-Agent": UA},
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def login(self) -> None:
        session = await self._ensure_session()
        login = BALANS_BASE + "/accounts/login/"
        try:
            async with session.get(login) as page:
                text = await page.text()
                if page.status != 200:
                    raise BalansConnectionError(f"HTTP {page.status}")
            match = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', text)
            if not match:
                raise BalansConnectionError("Inlogpagina niet leesbaar")
            async with session.post(
                login,
                data={"csrfmiddlewaretoken": match.group(1), "username": self._username, "password": self._password},
                headers={"Referer": login},
                allow_redirects=False,
            ) as reply:
                if reply.status in (301, 302, 303):
                    return
                if reply.status == 200:
                    raise BalansAuthError("Gebruikersnaam of wachtwoord geweigerd")
                raise BalansConnectionError(f"HTTP {reply.status}")
        except aiohttp.ClientError as err:
            raise BalansConnectionError(str(err)) from err

    async def current_flag(self) -> dict:
        """Geeft {'af': 0/1, 'ad': 'e'/'i'/'ie'/'', 's': kwartier} terug. Logt opnieuw in als het moet."""
        try:
            return await self._fetch()
        except BalansAuthError:
            await self.login()
            return await self._fetch()

    async def history(self) -> list[list]:
        """aFRR-kwartieren van de afgelopen ~26 uur (Balans geeft maximaal 27 uur terug): [[start_s, 'e'/'i'/'ie'/''], ...]."""
        now_ms = int(time.time() * 1000)
        start = (now_ms // QUARTER_MS) * QUARTER_MS - HISTORY_HOURS * 3_600_000
        try:
            payload = await self._get(start, now_ms)
        except BalansAuthError:
            await self.login()
            payload = await self._get(start, now_ms)
        events = payload.get("afrrEventIsps")
        if not isinstance(events, list):
            return []
        dirs: dict[int, str] = {}
        for item in payload.get("afrrDiscovery") or []:
            if isinstance(item, dict) and isinstance(item.get("start"), (int, float)):
                values = item.get("directions")
                if isinstance(values, list) and values:
                    dirs[int(item["start"])] = ("i" if "import" in values else "") + ("e" if "export" in values else "")
        out = []
        for quarter in sorted(set(int(q) for q in events if isinstance(q, (int, float)))):
            out.append([quarter // 1000, dirs.get(quarter, "")])
        return out

    async def soc_history(self, hours: float) -> list[list]:
        """Metingen uit het BE-dashboard (Balans bewaart ~25 uur): [[t_s, soc|None, net_W|None], ...].
        Hoe korter het venster, hoe fijner de resolutie (1 uur: 10 s, 6 uur: 1 min, 25 uur: 5 min)."""
        try:
            return await self._soc_rows(hours)
        except BalansAuthError:
            await self.login()
            self._installation = None
            return await self._soc_rows(hours)

    async def _installation_id(self) -> str:
        if self._installation:
            return self._installation
        session = await self._ensure_session()
        try:
            async with session.get(BALANS_BASE + "/customer/", allow_redirects=False) as page:
                if page.status in (301, 302, 303, 401, 403):
                    raise BalansAuthError("Sessie verlopen")
                text = await page.text()
        except aiohttp.ClientError as err:
            raise BalansConnectionError(str(err)) from err
        match = re.search(r'id=["\']current-history-config["\'][^>]*>(.*?)</script>', text, re.S)
        try:
            installation = json.loads(match.group(1)).get("installation") if match else None
        except ValueError:
            installation = None
        if not installation:
            raise BalansConnectionError("Installatie niet gevonden op het dashboard")
        self._installation = str(installation)
        return self._installation

    async def _soc_rows(self, hours: float) -> list[list]:
        installation = await self._installation_id()
        session = await self._ensure_session()
        now_ms = int(time.time() * 1000)
        try:
            async with session.get(
                BALANS_BASE + "/customer/current-history/api/",
                params={"installation": installation, "start": now_ms - int(hours * 3_600_000), "end": now_ms},
                headers={"Accept": "application/json", "Referer": BALANS_BASE + "/customer/"},
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as reply:
                if reply.status in (301, 302, 303, 401, 403):
                    raise BalansAuthError("Sessie verlopen")
                if reply.status == 409:  # andere installatie actief: opnieuw opzoeken
                    self._installation = None
                    raise BalansConnectionError("Installatie gewijzigd")
                if reply.status != 200 or "json" not in reply.headers.get("content-type", ""):
                    raise BalansConnectionError(f"HTTP {reply.status}")
                payload = await reply.json()
        except aiohttp.ClientError as err:
            raise BalansConnectionError(str(err)) from err
        rows = payload.get("rows") if isinstance(payload, dict) else None
        out = []
        for row in rows or []:
            if not isinstance(row, dict) or not isinstance(row.get("t"), (int, float)):
                continue
            soc = row.get("s") if isinstance(row.get("s"), (int, float)) and 0 <= row["s"] <= 100 else None
            grid = row.get("po") if isinstance(row.get("po"), (int, float)) and -60000 <= row["po"] <= 60000 else None
            if soc is not None or grid is not None:
                out.append([row["t"] / 1000, soc, grid])  # grid: netvermogen in W, + import / - export
        out.sort()
        return out

    async def _fetch(self) -> dict:
        now_ms = int(time.time() * 1000)
        quarter = (now_ms // QUARTER_MS) * QUARTER_MS
        payload = await self._get(quarter, now_ms)
        events = payload.get("afrrEventIsps")
        afrr = (1 if quarter in events else 0) if isinstance(events, list) else 0
        directions = ""
        sources = [item for item in payload.get("afrrDiscovery") or [] if isinstance(item, dict) and item.get("start") == quarter]
        sources += [item for item in payload.get("prices") or [] if isinstance(item, dict) and item.get("start") == quarter]
        for item in sources:
            values = item.get("directions")
            if isinstance(values, list) and values:
                directions = ("i" if "import" in values else "") + ("e" if "export" in values else "")
                break
        return {"af": afrr, "ad": directions, "s": quarter // 1000}

    async def _get(self, start_ms: int, end_ms: int) -> dict:
        session = await self._ensure_session()
        try:
            async with session.get(
                BALANS_BASE + "/customer/current-prices/api/",
                params={"start": start_ms, "end": end_ms},
                headers={"Accept": "application/json", "Referer": BALANS_BASE + "/customer/current-prices/"},
                allow_redirects=False,
            ) as reply:
                if reply.status in (301, 302, 303, 401, 403):
                    raise BalansAuthError("Sessie verlopen")
                if reply.status != 200 or "json" not in reply.headers.get("content-type", ""):
                    raise BalansConnectionError(f"HTTP {reply.status}")
                payload = await reply.json()
        except aiohttp.ClientError as err:
            raise BalansConnectionError(str(err)) from err
        if not isinstance(payload, dict):
            raise BalansConnectionError("Onverwacht antwoord")
        return payload
