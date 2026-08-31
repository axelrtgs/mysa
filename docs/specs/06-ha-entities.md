# 06 — Home Assistant entities

The integration reads values and capabilities from `pymysa` device objects. It contains
no protocol code and does not branch on model.

## Platforms

| platform | entity | condition |
|---|---|---|
| `climate` | thermostat | always |
| `sensor` | temperature, humidity | always |
| `sensor` | power, energy, current, voltage, duty cycle | `Capability.CURRENT` |
| `select` | fan speed, vertical swing | matching capability |
| `sensor` | signal strength | reported |
| `sensor` | electricity rate | the device's home carries `ERate` (spec 02) |
| `binary_sensor` | connectivity | always |
| `select` | horizontal swing | `Capability.HORIZONTAL_SWING` |
| `select` | temperature format | `Capability.TEMPERATURE_FORMAT` |
| `select` | sensor mode | `Capability.SENSOR_MODE` |
| `number` | active/idle brightness, setpoint min/max | `Capability.BRIGHTNESS`, `Capability.SETPOINT_LIMITS` |
| `switch` | lock, proximity | matching capability |
| `update` | firmware | always |

## Climate

| property | source |
|---|---|
| `hvac_modes` | capability discovery; always contains the reported mode |
| `fan_modes` | capability discovery |
| `swing_modes` | capability discovery |
| `current_temperature` | `current_temperature` field |
| `target_temperature` | `target_temperature` field |
| `current_humidity` | `humidity` field |
| `min_temp` / `max_temp` | `tempRange`, or the section's `lockoutMin` / `lockoutMax` |

Feature flags are computed from the declared capability set. A flag is set only when its
option list is non-empty.

## Scheduling

`schedule.holding`, `schedule.resolved` and `schedule.nextEvent` report whether a
schedule is in force and when it next acts (spec 08). The section exists only while a
schedule is assigned.

Home Assistant models scheduling through its own helpers rather than a device entity, so
the integration exposes the hold state as a switch where the device reports it, and the
next event as a timestamp sensor. Schedule definitions are not exposed: their shape is
not established.

## Identity

- `unique_id` is the Mysa device id.
- `has_entity_name` is set; entity names are per-entity and the device name comes from
  the device registry.

## Config flow

- Username and password authenticate against Cognito by SRP, once. The refresh token
  is stored in the config entry and renews the session thereafter; the password is
  stored only when the user enables silent reauthentication.
- Where the account holds more than one home, a second step lists them and asks which to
  set up, defaulting to all. The chosen ids are stored in the config entry and passed to
  `MysaAccount.limit_to` on every start, so an excluded device is neither created as an
  entity nor polled. An account with one home skips the step.
- Changing the selection in options reruns discovery: devices in a home that is no longer
  chosen are removed, and devices in a newly chosen one are added.
- `async_step_reauth` handles token failure.
- Options: polling interval.
- One `DataUpdateCoordinator` per account, polling `/state/batch`. A write refreshes the
  coordinator once the value is confirmed.
