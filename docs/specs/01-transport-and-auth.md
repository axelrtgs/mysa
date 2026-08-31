# 01 — Transport and authentication

## Authentication `[mit-sdk]`

AWS Cognito user pool authentication, followed by identity pool credentials for AWS IoT.

| constant | value |
|---|---|
| region | `us-east-1` |
| user pool id | `us-east-1_GUFWfhI7g` |
| client id | `19efs8tgqe942atbqmot5m36t3` |
| identity pool id | `us-east-1:ebd95d52-9995-45da-b059-56b865a18379` |
| login key | `cognito-idp.us-east-1.amazonaws.com/us-east-1_GUFWfhI7g` |

Libraries: `pycognito` (user pool), `boto3` (identity pool credentials), `awsiotsdk`
(AWS IoT MQTT). All three are synchronous and are called through an executor.

Sessions expire and are refreshed from the refresh token. Refresh failure raises an
authentication error which the integration surfaces as reauth.

## REST `[mit-sdk]`

| call | returns |
|---|---|
| `get_devices` | device records: `Model`, `SupportedCaps`, configuration fields |
| `get_device_states` | current state for all devices |
| `get_device_serial_number` | serial for one device |
| `get_device_firmwares` | available firmware versions |
| `get_homes` | home and grouping metadata |

## MQTT `[mit-sdk]`

AWS IoT over WebSocket, SigV4-signed with identity pool credentials.

- Credentials carry an expiry; the connection refreshes and reconnects before it passes.
- Reconnection uses bounded exponential backoff.
- Subscriptions are per device and are re-established after reconnect.

### Inbound message types

`DeviceV1Status`, `DeviceV2Status`, `DeviceAcStatus`, `DeviceStateChange`,
`DeviceSetpointChange`, `DevicePostBoot`, `DeviceLog`.

No V3 status type is defined upstream. BB-V3 status parsing is defined in spec 02 from
`[observed]` payloads.

### Outbound message types

`ChangeDeviceState`. Envelope in spec 03.

## Polling

MQTT is the primary source. HTTP polling at a configurable interval (default 120 s) is
the fallback.

Values carry timestamps. A value is accepted only when its timestamp is newer than the
currently held value for that field.
