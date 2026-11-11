"""Constanten voor Pool aFRR."""

DOMAIN = "pool_afrr"

BALANS_BASE = "https://dashboard.balansenergie.nl"
BROKER_PORT = 8883
TOPIC_PREFIX = "pool/afrr/"

CONF_HOST = "host"
CONF_BE_USERNAME = "be_username"
CONF_BE_PASSWORD = "be_password"
CONF_NAME = "name"
CONF_POOL_CODE = "pool_code"

POLL_SECONDS = 10
HEARTBEAT_SECONDS = 30
FLAG_TTL_SECONDS = 90
HISTORY_SECONDS = 300
HISTORY_KEEP_SECONDS = 48 * 3600

SIGNAL_UPDATE = "pool_afrr_update_{}"
