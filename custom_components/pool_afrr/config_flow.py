"""Config flow: één formulier met Balans-login, naam en poolcode."""

from __future__ import annotations

import ssl
import time
from typing import Any

import paho.mqtt.client as mqtt
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig, TextSelector, TextSelectorConfig, TextSelectorType

from .balans import BalansAuthError, BalansClient, BalansConnectionError
from .const import BROKER_PORT, CONF_BE_PASSWORD, CONF_BE_USERNAME, CONF_HOST, CONF_NAME, CONF_POOL_CODE, CONF_SOC, DOMAIN

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Required(CONF_BE_USERNAME): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        vol.Required(CONF_BE_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Required(CONF_NAME): TextSelector(),
        vol.Required(CONF_POOL_CODE): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Optional(CONF_SOC): EntitySelector(EntitySelectorConfig(domain="sensor")),
    }
)


def _test_broker(host: str, name: str, code: str) -> str | None:
    """Probeer kort te verbinden; geeft None bij succes, anders een foutsleutel."""
    result: dict[str, Any] = {}
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pool-test-{name}-{int(time.time())}")
    except AttributeError:
        client = mqtt.Client(client_id=f"pool-test-{name}-{int(time.time())}")

    def on_connect(_c, _u, _f, rc, _p=None):
        result["rc"] = rc if isinstance(rc, int) else getattr(rc, "value", 0)

    client.on_connect = on_connect
    client.username_pw_set(name, code)
    client.tls_set_context(ssl.create_default_context())
    try:
        client.connect(host, BROKER_PORT, 15)
    except Exception:  # noqa: BLE001
        return "broker_unreachable"
    deadline = time.time() + 10
    while "rc" not in result and time.time() < deadline:
        client.loop(timeout=0.5)
    try:
        client.disconnect()
    except Exception:  # noqa: BLE001
        pass
    if "rc" not in result:
        return "broker_unreachable"
    return None if result["rc"] == 0 else "broker_auth"


class PoolAfrrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            host = user_input[CONF_HOST].strip().removeprefix("mqtts://").removeprefix("https://").removeprefix("http://").split("/")[0].split(":")[0]
            user_input[CONF_HOST] = host
            user_input[CONF_NAME] = name
            await self.async_set_unique_id(name.lower())
            self._abort_if_unique_id_configured()
            balans = BalansClient(user_input[CONF_BE_USERNAME].strip(), user_input[CONF_BE_PASSWORD])
            try:
                await balans.login()
            except BalansAuthError:
                errors["base"] = "balans_auth"
            except BalansConnectionError:
                errors["base"] = "balans_unreachable"
            finally:
                await balans.close()
            if not errors:
                error = await self.hass.async_add_executor_job(_test_broker, host, name, user_input[CONF_POOL_CODE])
                if error:
                    errors["base"] = error
            if not errors:
                return self.async_create_entry(title=f"Pool aFRR · {name}", data=user_input)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return PoolOptionsFlow()


class PoolOptionsFlow(config_entries.OptionsFlow):
    """Later instellen welke SOC-sensor wordt gedeeld."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(CONF_SOC) or self.config_entry.data.get(CONF_SOC)
        schema = vol.Schema({vol.Optional(CONF_SOC, description={"suggested_value": current}): EntitySelector(EntitySelectorConfig(domain="sensor"))})
        return self.async_show_form(step_id="init", data_schema=schema)
