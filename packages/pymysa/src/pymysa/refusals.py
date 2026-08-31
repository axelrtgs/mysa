"""Classifying a refused write. See docs/specs/03-writes.md.

The backend refuses in two shapes, and they mean different things: a schema constraint
describes the request, a capability refusal describes the device. Neither is a defect.
"""

from __future__ import annotations

import json
import re

#: Fastify schema validation, e.g. "body/targetHeat/setpoint must be >= 5".
SCHEMA = re.compile(r'"code"\s*:\s*"FST_ERR_VALIDATION"')

#: A capability refusal names the feature and carries no code.
UNSUPPORTED = re.compile(r"is not supported", re.IGNORECASE)

REJECTED = "rejected"
UNSUPPORTED_KIND = "unsupported"
ERROR = "error"


def classify(message: str) -> tuple[str, str]:
    """Return the outcome kind and the reason worth recording."""
    reason = _reason(message)
    if UNSUPPORTED.search(message):
        return UNSUPPORTED_KIND, reason
    if SCHEMA.search(message):
        return REJECTED, reason
    return ERROR, reason


def _reason(message: str) -> str:
    """The backend's own words, without the envelope."""
    body = message[message.find("{") :] if "{" in message else message
    try:
        payload = json.loads(body)
    except ValueError:
        return message.strip()
    detail = payload.get("message", message)
    if isinstance(detail, list):
        return "; ".join(str(item) for item in detail)
    return str(detail)
