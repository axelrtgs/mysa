# 01 — Transport and authentication

## Cognito `[observed]`

| constant | value |
|---|---|
| region | `us-east-1` |
| user pool id | `us-east-1_GUFWfhI7g` |
| client id | `19efs8tgqe942atbqmot5m36t3` |

The app client permits two auth flows:

| flow | result |
|---|---|
| `USER_SRP_AUTH` | accepted |
| `REFRESH_TOKEN_AUTH` | accepted |
| `USER_PASSWORD_AUTH` | `InvalidParameterException: USER_PASSWORD_AUTH flow not enabled for this client` |

Login therefore requires the SRP handshake and is performed by `pycognito`, imported at
that call and nowhere else. The client has no secret, so no `SECRET_HASH` is sent.

Renewal is a plain HTTP call and uses no SDK:

```
POST https://cognito-idp.us-east-1.amazonaws.com/
Content-Type: application/x-amz-json-1.1
X-Amz-Target: AWSCognitoIdentityProviderService.InitiateAuth

{"AuthFlow":"REFRESH_TOKEN_AUTH","ClientId":"<client id>",
 "AuthParameters":{"REFRESH_TOKEN":"<token>"}}
```

The response carries `AuthenticationResult` with `IdToken`, `AccessToken` and
`ExpiresIn`. It carries no `RefreshToken`; the existing one remains in use.

A failed renewal raises an authentication error, which the integration surfaces as
reauth. A session is renewed once it is within 300 s of expiry.

## Host `[observed]`

`https://mysa-backend.mysa.cloud` serves every call.

`https://app-prod.mysa.cloud` is an older host still serving `/devices/firmware`. The
installed firmware version is in the state document (`identity.reported.fw`), so the
legacy host is not read.

## Headers `[observed]`

| header | value |
|---|---|
| `authorization` | the Cognito id token, unprefixed |
| `user-agent` | `okhttp/4.11.0` |

A request rejected with 401 or 403 raises an authentication error.

## Endpoints `[observed]`

| call | method | path | returns |
|---|---|---|---|
| devices | GET | `/devices` | `DevicesObj`, keyed by device id |
| state | POST | `/state/batch` | state document per device, keyed by device id |
| capabilities | GET | `/capabilities/{device_id}` | capability declaration |
| write | POST | `/state/{device_id}/update` | acknowledgement; see spec 03 |
| homes | GET | `/homes` | home and grouping metadata |
| update | GET | `/devices/update_available/{device_id}` | firmware update availability `[inferred]` |
| schedules | GET | `/schedules` | schedule definitions `[observed]` |
| home | GET | `/homes/{home_id}` | one home `[inferred]` |
| users | GET | `/users` | account record `[inferred]` |

`/state/batch` takes `{"deviceIds": ["<id>", ...]}` and returns every device in one call.

## Polling

One `/state/batch` call covers the account. State is polled at a configurable interval;
default 30 s.

Values carry timestamps. A value is accepted only when its timestamp is newer than the
currently held value for that field.
