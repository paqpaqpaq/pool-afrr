"""Minimale Balans Energie-client: inloggen en de aFRR-status van het lopende kwartier lezen."""

from __future__ import annotations

import re
import time

import aiohttp

from .const import BALANS_BASE

QUARTER_MS = 900_000
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

    async def _fetch(self) -> dict:
        session = await self._ensure_session()
        now_ms = int(time.time() * 1000)
        quarter = (now_ms // QUARTER_MS) * QUARTER_MS
        try:
            async with session.get(
                BALANS_BASE + "/customer/current-prices/api/",
                params={"start": quarter, "end": now_ms},
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
