# pymysa

Python SDK for Mysa smart thermostats. No Home Assistant dependency.

Devices are read and written through the Mysa cloud REST API. See `docs/specs/`.

## Install

Requires Python 3.12+.

```
python3 -m venv .venv && source .venv/bin/activate
pip install -e packages/pymysa
```

## Usage

The SDK holds state and the caller drives refresh: nothing here runs a timer.

```python
from pymysa import Capability, MysaAccount

account = await MysaAccount.login("me@example.com", password)
await account.discover()          # what exists and what it can do
await account.refresh()           # one /state/batch for every device

device = account.devices["device-42d6d24f"]
device.current_temperature        # 23.7
device.target_temperature         # the setpoint the current mode selects
device.mode, device.modes         # "off", ("off", "heat")

if device.supports(Capability.FAN):
    print(device.options(Capability.FAN))

await device.set_temperature(21)  # returns once the backend accepts it
await device.set_mode("heat")
await account.aclose()
```

An account with more than one home can be limited to some of them. `list_homes()` is one
request and discovers nothing, so the choice can be offered first:

```python
account = await MysaAccount.login(user, password)
homes = await account.list_homes()
account.limit_to([home_id])       # or MysaAccount(..., homes=[home_id])
await account.discover()          # only that home's devices, and only those get polled
```

A property the device does not report reads `None`. `None` and `0` are distinct: a
device reporting 0 A is reporting a measurement.

A setter returns as soon as the write is accepted, with the written value already
readable, and confirms in the background. A write can be accepted with 200 and never
applied — an AC applies only the setpoint its current mode selects — so if it never
lands, the value reverts and `on_write_failed` is called:

```python
account = await MysaAccount.login(user, password, on_write_failed=log_it)
await device.set_temperature(21, wait=True)   # or block until confirmed
```

`ValueRefused` is the backend refusing the value; `UnsupportedCommand` is the device not
having the feature. Both are `MysaError`.

See `docs/specs/09-sdk-surface.md` for the whole surface.

## Debug harness

`inspect` reports what each device on the account carries, and flags any field not in
the catalogue:

```
pymysa-debug inspect
pymysa-debug inspect --device <id>
```

`exercise` writes every parameter a device supports, confirms it by reading it back, and
puts it back. It ends with a per-device pass or fail, every failure with its reason, and
anything left changed:

```
pymysa-debug exercise
pymysa-debug exercise --device <id> --yes
```

Both write raw captures to `docs/samples/raw/<model>/<read|write>/<device id>.json`.
Raw carries device ids, serials and names, and is gitignored.

`process` redacts them into `docs/samples/<model>/<read|write>/<alias>.json`, which is
what a pull request adding a model carries:

```
pymysa-debug process
```

Add `-v` to log pymysa's own HTTP activity. It does not raise third-party loggers, which
log full request bodies at DEBUG including the Cognito id token.

## Credentials

`MYSA_USERNAME` / `MYSA_PASSWORD`, or an interactive prompt. Never written to a sample.

The Cognito app client permits SRP for login and `REFRESH_TOKEN_AUTH` for renewal.
`pycognito` is imported only for the initial login; a restored session renews over plain
HTTP.

## Session cache

The refresh token is written `0600` to `$XDG_CACHE_HOME/pymysa/session.json`
(default `~/.cache/pymysa/session.json`), outside any repository. The password is not
stored.

`--login` bypasses the cache. `--session <path>` relocates it. An unreadable, malformed
or unrefreshable cache falls back to a prompt.
