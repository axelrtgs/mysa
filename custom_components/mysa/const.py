"""Constants. See docs/specs/06-ha-entities.md."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "mysa"
MANUFACTURER: Final = "Mysa"

CONF_HOMES: Final = "homes"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_STORE_PASSWORD: Final = "store_password"

DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 3600

#: One request per device, answering something that moves a few times a year (spec 06).
FIRMWARE_INTERVAL: Final = timedelta(hours=24)
