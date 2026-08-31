"""Device objects. See docs/specs/09-sdk-surface.md."""

from __future__ import annotations

from .base import MysaDevice
from .declaration import OBSERVED_MODES
from .maps import FIELDS, Source, semantics
from .readings import Readings
from .writing import CONFIRM_INTERVAL, CONFIRM_TIMEOUT

#: Models with a field map. A model absent from it is built anyway, on no map: it reports
#: what it reports, and every semantic name reads None until the model is described.
KNOWN_MODELS = frozenset(FIELDS)

__all__ = [
    "CONFIRM_INTERVAL",
    "CONFIRM_TIMEOUT",
    "FIELDS",
    "KNOWN_MODELS",
    "OBSERVED_MODES",
    "MysaDevice",
    "Readings",
    "Source",
    "semantics",
]
