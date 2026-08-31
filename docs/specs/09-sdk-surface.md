# 09 — SDK surface

What `pymysa` exposes to a caller. Home Assistant is one caller; nothing here is shaped
for it, and the integration adds no protocol code of its own (spec 00).

## Ownership

The SDK holds state and the caller drives refresh. `MysaAccount` caches the last
`/state/batch` and the device records behind it; device objects read that cache. Nothing
in the SDK runs a timer.

The transport is poll-only (spec 01), so there is nothing to push and no reason for the
SDK to own a loop. Home Assistant's `DataUpdateCoordinator` already polls on an interval,
backs off, and marks entities unavailable; a second timer inside the SDK would duplicate
it and add a lifecycle to unwind on every reload.

## Account

```python
account = await MysaAccount.login(username, password)
await account.discover()          # /devices, /capabilities/{id}, /homes, /schedules
await account.refresh()           # /state/batch for every known device
device = account.devices["ccddeeff0011"]
await account.aclose()
```

| member | meaning |
|---|---|
| `MysaAccount.login(username, password, session=None)` | SRP login, then a client over that session |
| `list_homes()` | the account's homes, one request, no device discovery |
| `limit_to(home_ids)` | take only devices in these homes; `None` takes every home |
| `MysaAccount(auth, session)` | for a caller holding its own auth, as the config flow does |
| `discover()` | device records, capability documents, homes and schedules; identity only |
| `refresh()` | one `/state/batch` for every discovered device |
| `devices` | `Mapping[str, MysaDevice]`, keyed by device id |
| `schedules` | `tuple[Schedule, ...]`, from the last `discover()` |
| `homes` | `Mapping[str, Home]`; `home_of(device)` is the one a device belongs to |
| `included_homes` | the homes discovery is limited to, or `None` |
| `refresh_firmware()` | update availability for every discovered device |
| `aclose()` | closes the session where the account opened it |

`discover()` is identity and capability: what exists and what it can do. `refresh()` is
state: what it is doing. A caller that only ever needs the second still calls the first
once, because a device object cannot be built without its record.

### Firmware

`refresh_firmware()` is separate from `discover()` because it costs one request per
device and answers a question that changes on the backend's schedule, not the account's.
A caller that wants it asks for it; discovery does not pay for it.

A device that cannot be read is left as it was: a BB-V3-0 returns 500 for its own
`/devices/update_available` and is a working device with an unknown answer, which
`firmware_update` reports as `None` rather than as no update. `[observed]`

### Limiting to a home

An account can hold more than one home, and a caller usually wants one of them.

```python
account = await MysaAccount.login(username, password)
homes = await account.list_homes()        # one request, no devices
account.limit_to(["0a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d"])
await account.discover()
```

`list_homes()` exists so the choice can be offered before anything is discovered:
discovery reads a capability document per device, and a caller about to exclude most of
them should not pay for them first.

The limit applies from the next `discover()`, which drops the devices it now excludes -
so widening it brings them back and narrowing it takes them away, without rebuilding the
account. `refresh()` reads only what discovery kept, which is the point: an excluded
device costs nothing per poll.

A device whose record names no home is in no home, and a caller that asked for one home
did not ask for it. A limit naming a home the account does not have is logged by id
rather than silently returning nothing.

The limit can also be given at construction, for a caller restoring a stored choice:
`MysaAccount(auth, session, homes=[...])`.

Discovery tolerates a per-device failure. An AC-V1-0 returns 404 for its capability
document (spec 04) and is discovered with none; a device whose record cannot be read at
all is omitted and named in `account.unavailable`.

## Device

A `MysaDevice` is a live view of the cache, not a snapshot: the same object reflects the
next `refresh()`. Identity is stable, so a caller may hold it.

| member | meaning |
|---|---|
| `id`, `name`, `model`, `firmware`, `serial`, `home_id` | identity |
| `available` | the device reports itself connected |
| `capabilities` | `frozenset[Capability]` |
| `supports(capability)` | membership test |
| semantic properties | spec 02 field maps, resolved against the cache |
| `set_*()` | writes, below |
| `setpoint_range` | the bounds a setpoint write must fall inside, for the section the mode selects |
| `setpoint_step` | the resolution a setpoint is accepted at |
| `firmware_update` | update availability, after `refresh_firmware()` |
| `raw` | the device's own `/state/batch` document, for a caller that needs a field the SDK does not name |

A semantic property whose field the device does not report is `None`. Absent values are
never defaulted or estimated (spec 00), so `None` and `0` stay distinct.

### Semantic properties

The names are those in spec 02's field maps. Which of them a model carries follows from
its field map; a caller reads `None` for the rest rather than branching on model.

Enumerated values are exposed by name where a name is established (spec 02): `mode`
returns `"heat"`, and `mode_value` returns `4` for a caller that wants the wire value.
A value with no established name reads as `None` from `mode` and its number from
`mode_value`, so an unmapped value is visible rather than silently absent.

### Setpoint bounds

`min_setpoint` and `max_setpoint` are the lockout pair a device reports, which is a
setting: they are what `Capability.SETPOINT_LIMITS` writes. `setpoint_range` answers a
different question - what a write may contain - and resolves in order:

1. `lockoutMin` and `lockoutMax` in the section the current mode selects, where that
   section reports them;
2. the range the device declares: `climateControl.heat.setpoint` in the capability
   document, or `SupportedCaps.tempRange` on an AC unit;
3. `None`, where neither is served.

It follows the mode for the same reason `set_temperature` does (spec 03): the bounds are
a property of the section being written, and an AC unit's `targetCool` carries no lockout
pair while its `targetHeat` carries 19-24. Bounding a cool setpoint by the heat section's
lockout would refuse setpoints the device accepts.

`setpoint_step` is 0.5 for every device (spec 03). Both baseboards declare
`climateControl.heat.setpoint` as 5, 5.5, 6 ... 30, which is where the number comes from;
an AC unit declares no step and is written at the same resolution. `[observed]`

## Capabilities

```python
class Capability(Enum):
    HEAT, COOL, FAN, VERTICAL_SWING, HORIZONTAL_SWING,
    CURRENT, ENERGY, LOCK, PROXIMITY, BRIGHTNESS, TEMPERATURE_FORMAT,
    SENSOR_MODE, SETPOINT_LIMITS, SCHEDULE
```

A capability is declared from three sources in order (spec 04): the capability document
where the device serves one, the codeset declaration for AC units, and otherwise the
sections and fields present in the state document.

A capability whose option set resolves fewer than two values is not declared: a control
with one option is not a control. A BB-V1-0 declares `trackingSensor` writable with
`internal` as its only value, and nothing is exposed for it.

`options(capability)` returns the values a control accepts, by name where names are
established. Two rules narrow the declared set first:

- A declaration can name values the state field holds as numbers - `climateControl.mode`
  declares `off` and `heat` for a field holding 0 and 4. The names are translated to the
  values the field holds before anything compares or writes them.
- A declared value that translates to nothing the field could hold is dropped. A control
  offering it would build a selector whose every selection the backend refuses:
  `sensing.temperature.trackingSensor` declares `internal` and `remote` for a field
  holding 0, and until those names are tied to numbers there is nothing to offer.

A field the device reports with no counterpart in its section's `desired` half is not a
control either, whatever it looks like: the backend holds no desired value for it and
drops the write (spec 02).

## Writes

Every setter posts one shadow section (spec 03) and returns once the backend has
accepted it.

```python
await device.set_temperature(21)              # returns after the write is accepted
await device.set_temperature(21, wait=True)   # returns after it is confirmed
```

On acceptance the SDK records the written value in the cache as pending, so a property
read reflects it before the next `refresh()`. A confirmation runs in the background:
`/state/batch` is polled until `reported` carries the value or the timeout lapses. If it
never lands, the pending value is dropped — the property returns to what the device
actually holds — and `on_write_failed` is called with the device, the field and the
value.

That covers the accepted-and-not-applied case (spec 03), which is common: an AC applies
only the setpoint its current mode selects, and a control the codeset cannot express is
accepted and ignored. A caller that treats 200 as success shows the user a value the
device never took.

| refusal | raised |
|---|---|
| schema validation (`FST_ERR_VALIDATION`) | `ValueRefused`, carrying the constraint |
| capability refusal | `UnsupportedCommand`, carrying the named feature |
| accepted, never applied | not raised; `on_write_failed` after the confirmation window |

A write of a value the device's own capability document does not declare is refused
locally, before the request. The backend accepts such a write with 200 and never applies
it, which is indistinguishable at the transport from a device that simply declined.

### Setters

| setter | section |
|---|---|
| `set_temperature(c)` | the setpoint the current mode selects |
| `set_heat_setpoint(c)` / `set_cool_setpoint(c)` | `targetHeat` / `targetCool` |
| `set_mode(name)` | `modes.mode` |
| `set_fan_speed(name)`, `set_vertical_swing(name)`, `set_horizontal_swing(name)` | `modes` |
| `set_lock(name)`, `set_proximity(bool)`, `set_brightness(active, idle)` | `physicalInterface` |
| `set_temperature_format(name)` | `physicalInterface.format` |
| `set_setpoint_limits(low, high)` | the active setpoint section |

`set_temperature` follows the mode because that is what the device does (spec 03): on a
unit carrying both setpoint sections, the one the mode does not select is accepted and
ignored. A caller that wants a specific section names it.

## Schedules

Read-only, plus one write.

| member | meaning |
|---|---|
| `account.schedules` | schedule records from `/schedules` |
| `device.schedule` | hold state: `holding`, `resolved`, `next_event`, or `None` where the device has no schedule |
| `device.schedule.release()` | writes `holding: false` |

`release()` is one-way and says so: ending a hold is a write, and nothing observed starts
one (spec 08). Schedule definitions are not exposed; their shape is not established.

## Sessions

`MysaAuth.from_refresh_token(username, refresh_token, session)` builds auth from a stored
refresh token, for a caller that logged in once and kept the token rather than the
password. The first request renews the session; nothing about the SRP login is needed
again, and pycognito is never imported.

## Errors

| exception | raised when |
|---|---|
| `AuthenticationError` | credentials rejected, or a session that cannot be renewed |
| `TransportError` | the request failed or returned an unexpected status |
| `ValueRefused` | the backend refused the value against its schema |
| `UnsupportedCommand` | the device does not have the feature, locally or per the backend |

`ValueRefused` and `UnsupportedCommand` are both `MysaError`. A caller that cannot tell
them apart still catches both.
