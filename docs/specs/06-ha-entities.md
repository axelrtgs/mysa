# 06 — Home Assistant entities

The integration reads values and capabilities from `pymysa` device objects. It contains
no protocol code and does not branch on model: where it needs to know something about a
device, the SDK is what tells it (spec 00).

## Setup

One config entry is one Mysa account. Setup restores the stored session, applies the
stored home selection with `account.limit_to()`, calls `discover()` once, then hands the
account to a single `DataUpdateCoordinator` that calls `await account.refresh()` on the
polling interval. The SDK owns no timer; the coordinator is the only clock (spec 09).

A device in a home the entry does not include is neither created nor polled, because
`limit_to` runs before discovery and `refresh()` reads only what discovery kept.

| setting | default | where |
|---|---|---|
| polling interval | 60 seconds | options |
| homes | every home | options; the config flow asks where there is more than one |

A poll that has not returned within the polling interval is abandoned and the update
fails. Home Assistant's shared session allows five minutes, and a coordinator will not
start a refresh while one is in flight, so a slow read would otherwise stop the entry
updating for as long as it hangs, silently.

`refresh_firmware()` runs at setup and then at most once every 24 hours, from inside the
coordinator's update: it costs one request per device (spec 09) to answer something that
moves a few times a year.

## Entities

An entity exists where the device declares the capability behind it, or - for a
measurement, which is not a capability - where the device reports the value at setup. A
value that is `None` at setup creates nothing; a value that becomes `None` later makes
its entity unavailable (spec 05). The two rules differ because a capability is a
statement about the device and a reading is a statement about one poll.

An option list narrows this further: a capability whose `options()` is empty or single
creates no entity, because a control with one option is not a control (spec 09).

| platform | entity | condition |
|---|---|---|
| `climate` | thermostat | always |
| `sensor` | temperature, humidity | the value is reported |
| `sensor` | current, voltage, power, duty cycle, energy, power consumed | each on its own value |
| `sensor` | signal strength | the value is reported |
| `sensor` | electricity rate | the device's home carries `ERate` (spec 02) |
| `sensor` | next schedule event | the device carries a `schedule` section |
| `binary_sensor` | connectivity | always |
| `binary_sensor` | firmware update available | `refresh_firmware()` read an answer |
| `binary_sensor` | schedule hold | the device carries a `schedule` section |
| `select` | keypad lock | `Capability.LOCK` |
| `select` | temperature format | `Capability.TEMPERATURE_FORMAT` |
| `switch` | proximity wake, adaptive brightness, Climate+ | matching capability |
| `number` | active brightness, idle brightness | `Capability.BRIGHTNESS` |
| `number` | setpoint minimum, setpoint maximum | `Capability.SETPOINT_LIMITS` |
| `button` | release schedule hold | a hold is in force; added and removed as one comes and goes |

Fan speed, vertical swing and horizontal swing are properties of the climate entity, not
separate selects: Home Assistant's climate entity carries all three, and a second entity
for the same control would be a second thing to keep in step with the first.

### Identity

`unique_id` is the Mysa device id for the climate entity, and `<device id>-<key>` for
every other entity, where `key` is the name in the tables below. The scheme is fixed:
changing it later would strand every entity a user already has, because Home Assistant
matches on `unique_id` and creates a fresh entity for one it has not seen.

`has_entity_name` is set. Entity names are per-entity; the device name comes from the
device registry, whose entry carries the Mysa device id as its identifier, the model,
the firmware as `sw_version` and the serial where the model reports one.

A Mysa device id is the device's MAC address, so the registry entry also carries it as a
MAC connection. Home Assistant links registry entries that share one, which is what puts
the thermostat and its network client - a UniFi client, say - on each other's pages. An
id that is not twelve hex characters is not registered as a MAC: a connection nothing
owns would match whatever else guessed the same string.

An entity is available when the last coordinator update succeeded, the device reports
itself connected, and its own value is not `None`.

## Climate

| property | source |
|---|---|
| `hvac_modes` | `device.modes`, mapped to `HVACMode`; always contains the reported mode |
| `hvac_mode` | `device.mode`, or `None` where the reported value has no established name |
| `fan_modes` | `device.options(Capability.FAN)` |
| `swing_modes` | `device.options(Capability.VERTICAL_SWING)` |
| `swing_horizontal_modes` | `device.options(Capability.HORIZONTAL_SWING)` |
| `current_temperature` | `device.current_temperature` |
| `target_temperature` | `device.target_temperature` |
| `current_humidity` | `device.humidity` |
| `min_temp` / `max_temp` | `device.setpoint_range` (spec 09) |
| `target_temperature_step` | `device.setpoint_step` |

`temperature_unit` is always Celsius. `physicalInterface.format` is what the device's own
display shows and does not change what the protocol carries (spec 02); it is a select,
not the entity's unit.

Mysa modes map to Home Assistant's by name: `off`, `auto`, `cool`, `heat`, `fan only`
and `dry` become `off`, `auto`, `cool`, `heat`, `fan_only` and `dry`. A mode value with
no established name (spec 02) is not offered and reads as no mode rather than as `off`.

Feature flags follow the declared set: `TARGET_TEMPERATURE` where the device carries a
setpoint, `FAN_MODE`, `SWING_MODE` and `SWING_HORIZONTAL_MODE` where the matching
capability resolves to two or more options, and `TURN_ON` / `TURN_OFF` where the mode
list contains `off` and at least one other mode.

## Sensors

| key | source | unit | class |
|---|---|---|---|
| `temperature` | `current_temperature` | °C | temperature, measurement |
| `humidity` | `humidity` | % | humidity, measurement |
| `current` | `current` | mA | current, measurement |
| `voltage` | `voltage` | V | voltage, measurement |
| `power` | `wattage` | W | power, measurement |
| `duty_cycle` | `duty_cycle` | % | measurement, diagnostic |
| `energy` | `energy` | kWh | energy, total increasing |
| `power_consumed` | `power_consumed` | none | measurement, diagnostic |
| `signal_strength` | `signal_strength` | dBm | signal strength, measurement, diagnostic |
| `electricity_rate` | the home's `ERate` | none | diagnostic |
| `schedule_next_event` | `device.schedule.next_event` | | timestamp, diagnostic |
| `last_reported` | `device.last_connected` | | timestamp, diagnostic |

`energy` is declared as kilowatt hours on evidence that does not exist yet, which is
what puts it on the energy dashboard; `power_consumed` is declared with no unit for the
same absence of evidence. Spec 05 records why the two differ and what settles it.

`last_reported` is when the device itself last spoke to the backend, which is not when
the integration last polled. The two answer different questions, and only the first says
whether a value that looks stuck is stuck at the device, in the backend, or here.

`electricity_rate` carries no currency: the payload serves a bare number and names no
currency anywhere (spec 02). It is a diagnostic value, and no cost is derived from it -
Home Assistant applies its own rate to the energy the integration supplies.

## Binary sensors

| key | source | class |
|---|---|---|
| `connected` | `device.available` | connectivity |
| `schedule_hold` | `device.schedule.holding` | running, diagnostic |
| `firmware_update` | `device.firmware_update.available` | update, diagnostic |

The firmware entity reports and does not install: no install path has been observed on
any surface this project reads, so an `update` entity's only button would do nothing.

## Selects, switches and numbers

| platform | key | source | writes |
|---|---|---|---|
| `select` | `lock` | `device.lock` | `set_lock(option)` |
| `select` | `temperature_format` | `device.temperature_format` | `set_temperature_format(option)` |
| `switch` | `proximity` | `device.proximity` | `set_proximity(bool)` |
| `switch` | `adaptive_brightness` | `device.brightness_mode` | `set_adaptive_brightness(bool)` |
| `switch` | `thermostatic` | `device.thermostatic` | `set_thermostatic(bool)` |
| `number` | `active_brightness` | `device.active_brightness` | `set_brightness(active=...)` |
| `number` | `idle_brightness` | `device.idle_brightness` | `set_brightness(idle=...)` |
| `number` | `min_setpoint` | `device.min_setpoint` | `set_setpoint_limits(low, high)` |
| `number` | `max_setpoint` | `device.max_setpoint` | `set_setpoint_limits(low, high)` |

Keypad lock is a select and not a switch: it holds three values on a BB-V3-0 - unlocked,
limited to the lockout range, and full - and a switch cannot say which of the two locked
states is in force (spec 02).

Brightness is 0-100. The setpoint limits are whole degrees bounded by `setpoint_range`,
and each writes the pair, because `set_setpoint_limits` takes both: the entity being
moved supplies its new value and the other supplies its current one.

Adaptive brightness is the one switch gated on the capability document rather than on
the device reporting a writable field: a BB-V1-0 carries `intensityMode` in `desired`,
takes the write and reads it back, and has no light sensor (spec 03).

## The schedule hold

A hold is released and not created: writing `holding: false` ends one, and nothing
observed starts one, because whatever creates a hold carries the setting being held and
the state document does not (spec 08).

So it is a `button` that releases, alongside a timestamp sensor for the next event. A
switch would offer a control whose other half cannot work.

Schedule definitions are not exposed. Their shape is not established: every capture's day
lists are empty (spec 08).

The button exists only while there is a hold to release, and appears and disappears with
one. A button's state is the timestamp of its last press, so there is no history to
protect by keeping it around unavailable, and a button that cannot do anything is worse
than no button.

What deserves history is the hold itself, which is a binary sensor: whether one is in
force, kept across the schedule being deleted and recreated. The next-event timestamp is
the same - both go unavailable when the section does, rather than disappearing.

## Writes

A setter returns as soon as the backend accepts it, with the written value already
readable from the device object (spec 09). The entity writes its state at that point and
asks the coordinator for a refresh, so the user sees the new value immediately and the
next poll replaces it with what the device reports.

Confirmation runs in the SDK. If a write never lands, the SDK drops the pending value and
calls `on_write_failed`; the integration passes that callback when it constructs the
account, and the callback updates every entity on the coordinator, so the value in the UI
snaps back to what the device actually holds. It is logged as a warning naming the device
and the field, because a control that silently does nothing otherwise looks like one that
works.

A setpoint written while the thermostat is off is refused before the request. The field
moves and the device does nothing with it, which is the same trap spec 03 describes; the
app will not let you set one either.

| refusal | surfaces as |
|---|---|
| `ValueRefused` | `ServiceValidationError` - the value was wrong |
| `UnsupportedCommand` | `HomeAssistantError` - the device does not have the feature |
| accepted, never applied | the callback above; no exception |

## Missing fields

At setup, `current_temperature`, `target_temperature` and `mode` are checked and any that
resolve to `None` are logged once at error with the device and the model: an unavailable
thermostat with no explanation sends the user looking at their network.

`connected`, the fourth critical field (spec 02), is not checked. A device that reports
no connection state and one that reports itself offline read the same, and the
connectivity entity is what says which.

## Config flow

- Username and password authenticate against Cognito by SRP, once. The refresh token is
  stored in the config entry and renews the session thereafter. The password is stored
  only when the user asks for it, and only to reauthenticate without being prompted.
- The account's unique id is the username, so one account cannot be set up twice.
- Where the account holds more than one home, a second step lists them and asks which to
  set up, defaulting to all. `list_homes()` is one request and discovers nothing, so the
  question is asked before anything is discovered rather than after (spec 09). An account
  with one home skips the step.
- Options carry the home selection and the polling interval. Changing either reloads the
  entry, which reruns discovery: devices in a home that is no longer chosen are removed
  and devices in a newly chosen one are added. Removal is real: a device the new
  discovery does not return is dropped from the device registry, which takes its
  entities with it - otherwise it stays in the UI as an unavailable thermostat.
- `async_step_reauth` handles a session that cannot be renewed, and asks for the password
  again unless one is stored.

## Not exposed

| what | why |
|---|---|
| sensor mode | `tracking.tracking` holds numbers and its declared names, `internal` and `remote`, are tied to none of them; a selector built from it would refuse every selection (spec 09) |
| heater type, brightness mode, early-on, ambient offset, tracking mode | informational (spec 02): read and mapped, not surfaced |
| `hvac_action` | nothing reports whether the element is on now. Duty cycle is an average over the device's reporting interval, and reading it as an instantaneous state is an inference, not a measurement |
| schedule definitions | not established (spec 08) |
| smart alerts | set per home, and where the home holds them is not established (spec 02) |
