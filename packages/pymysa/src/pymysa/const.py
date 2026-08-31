"""Protocol constants. See docs/specs/01-transport-and-auth.md and 03-commands.md."""

from __future__ import annotations

from enum import IntEnum

AWS_REGION = "us-east-1"
COGNITO_USER_POOL_ID = "us-east-1_GUFWfhI7g"
COGNITO_CLIENT_ID = "19efs8tgqe942atbqmot5m36t3"

# The app client permits SRP for login and REFRESH_TOKEN_AUTH for renewal; plain
# USER_PASSWORD_AUTH is rejected with "flow not enabled for this client". Renewal is
# therefore a plain signed-free POST, while login needs the SRP handshake.
COGNITO_IDP_URL = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/"
INITIATE_AUTH_TARGET = "AWSCognitoIdentityProviderService.InitiateAuth"
AMZ_JSON = "application/x-amz-json-1.1"

# Two REST hosts. The backend serves devices, state and capabilities; firmware is only
# on the older host.
API_BASE_URL = "https://mysa-backend.mysa.cloud"
LEGACY_BASE_URL = "https://app-prod.mysa.cloud"

CLIENT_HEADERS = {
    "user-agent": "okhttp/4.11.0",
    "accept": "application/json",
}
ENVELOPE_VERSION = "1.0"
BODY_VERSION = 1
SRC_TYPE = 100
DEST_TYPE = 1
RESP = 2
APPLY_NOW = -1


class Mode(IntEnum):
    OFF = 1
    AUTO = 2
    HEAT = 3
    COOL = 4
    FAN_ONLY = 5
    DRY = 6


class FanSpeed(IntEnum):
    AUTO = 1
    LOW = 3
    MEDIUM = 5
    HIGH = 7
    MAX = 8


class Swing(IntEnum):
    STILL = 1
    AUTO = 2


class KeyId(IntEnum):
    """SupportedCaps key ids. See docs/specs/04-capabilities.md."""

    FAN_AUTO = 8
    FAN_LOW = 9
    FAN_MEDIUM = 10
    FAN_HIGH = 11
    SWING_V_TOGGLE = 12
    SWING_V_ON = 39
    SWING_V_OFF = 40
    SWING_K = 47


FAN_KEYS: dict[KeyId, FanSpeed] = {
    KeyId.FAN_AUTO: FanSpeed.AUTO,
    KeyId.FAN_LOW: FanSpeed.LOW,
    KeyId.FAN_MEDIUM: FanSpeed.MEDIUM,
    KeyId.FAN_HIGH: FanSpeed.HIGH,
}

VERTICAL_SWING_KEYS = frozenset(
    {KeyId.SWING_V_TOGGLE, KeyId.SWING_V_ON, KeyId.SWING_V_OFF, KeyId.SWING_K}
)

CAPS_MODE_IDS: dict[int, Mode] = {
    2: Mode.AUTO,
    3: Mode.HEAT,
    4: Mode.COOL,
    5: Mode.FAN_ONLY,
    6: Mode.DRY,
}
