"""Constants for the MG iSmart India integration."""

from __future__ import annotations

from datetime import timedelta
import logging

DOMAIN = "mg_ismart_india"
LOGGER = logging.getLogger(__package__)

CONF_PHONE = "phone"
CONF_PASSWORD = "password"
CONF_VIN = "vin"
CONF_PIN = "pin"
CONF_PIN_HASH = "pin_hash"

TAP_LOGIN_URL = "https://iov-tap.mgindia.co.in/TAP.Web/ota.mp"
TAP_STATUS_URL = "https://iov-tap.mgindia.co.in/TAP.Web/ota.mpv21"
GATEWAY_BASE_URL = "https://iov-gateway.mgindia.co.in/api.app/v1"
USER_AGENT = "CER_IKE_01/2.3.0 (iPad; iOS 26.3; Scale/2.00)"

UPDATE_INTERVAL = timedelta(minutes=15)
STATUS_POLL_ATTEMPTS = 6
STATUS_POLL_DELAY = 1
CONTROL_POLL_ATTEMPTS = 8
CONTROL_POLL_DELAY = 3

PLATFORMS = [
    "sensor",
    "binary_sensor",
    "climate",
    "lock",
    "cover",
    "button",
    "select",
]
