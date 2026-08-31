# 06 — Home Assistant entities

The integration reads values and capabilities from `pymysa` device objects. It contains
no protocol code and does not branch on model.

## Platforms

| platform | entity | condition |
|---|---|---|
| `climate` | thermostat | always |
| `sensor` | temperature, humidity | always |
| `sensor` | power, energy, current, voltage, duty cycle | `Capability.CURRENT` |
| `sensor` | signal strength, electricity rate | reported |
| `binary_sensor` | connectivity | always |
| `select` | horizontal swing | `Capability.HORIZONTAL_SWING` |
| `select` | temperature format | `Capability.TEMPERATURE_FORMAT` |
| `select` | sensor mode | `Capability.SENSOR_MODE` |
| `number` | brightness min/max, setpoint min/max | `Capability.BRIGHTNESS`, `Capability.SETPOINT_LIMITS` |
| `switch` | lock, auto brightness, proximity, eco | matching capability |
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
| `min_temp` / `max_temp` | `tempRange` or device default |

Feature flags are computed from the declared capability set. A flag is set only when its
option list is non-empty.

## Identity

- `unique_id` is the Mysa device id.
- `has_entity_name` is set; entity names are per-entity and the device name comes from
  the device registry.

## Config flow

- Username and password authenticate against Cognito. Tokens are stored in the config
  entry; the password is stored only when the user enables silent reauthentication.
- `async_step_reauth` handles token failure.
- Options: polling interval.
- One `DataUpdateCoordinator` per account. MQTT messages push into it; HTTP polling is
  the fallback.
