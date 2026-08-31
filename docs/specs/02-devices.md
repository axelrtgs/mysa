# 02 — Devices

Each device class declares its own model prefixes, command type, field map, value
wrapping and capabilities. Nothing outside the class inspects the model string.

## Device contract

```python
class MysaDevice(ABC):
    MODEL_MATCH: ClassVar[ModelMatch]        # prefix, and suffix where it disambiguates
    COMMAND_TYPE: ClassVar[int | None]       # MQTT body.type; None = writes unsupported
    WRAPPED_FIELDS: ClassVar[frozenset[str]] # protocol keys carrying {"v":..,"t":..}
    FIELDS: ClassVar[FieldMap]               # semantic name -> protocol key
    CAPABILITIES: ClassVar[frozenset[Capability]]
    VERIFIED: ClassVar[bool]
```

`FIELDS` maps one semantic name to one protocol key per device. Where a device reports
the same value under more than one key, the class names the authoritative one.

`WRAPPED_FIELDS` lists the keys that arrive as `{"v": value, "t": timestamp}` for that
device. Unwrapping is declared, not detected.

`CAPABILITIES` is the static set. Devices whose capabilities depend on runtime data
(AC units, spec 04) override `capabilities()` and extend the static set.

## Model registry

| model | product | command type | verified |
|---|---|---|---|
| `BB-V1-*` | Baseboard V1 | 1 `[mit-sdk]` | yes |
| `BB-V2-*` (no `-L`) | Baseboard V2 | 4 `[mit-sdk]` | no |
| `BB-V2-*-L` | Baseboard V2 Lite | 5 `[mit-sdk]` | no |
| `BB-V3-*` | Baseboard V3 | unknown | reads only |
| `AC-V1-*` | Mini-split controller | 2 `[mit-sdk]` | yes |
| `INF-V1-*` | In-floor | unknown | no |
| `ST-V1-*` | Central HVAC | unknown | no |

Matching is on prefix. The `-L` suffix takes a different command type from the full V2
and is matched explicitly.

## Field maps

### BB-V1 `[observed]`

| semantic | key | wrapped |
|---|---|---|
| `current_temperature` | `CorrectedTemp` | yes |
| `raw_temperature` | `SensorTemp` | yes |
| `target_temperature` | `SetPoint` | no |
| `humidity` | `Humidity` | yes |
| `mode` | `TstatMode` | no |
| `current` | `Current` | no |
| `voltage` | `Voltage` | no |
| `duty_cycle` | `Duty` | no |
| `max_current` | `MaxCurrent` | no |
| `heatsink_temperature` | `HeatSink` | no |
| `signal_strength` | `Rssi` | no |
| `connected` | `Connected` | no |
| `lock` | `Lock` | no |
| `brightness` | `Brightness` | no |
| `firmware` | `fw` | no |

`MaxCurrent` is a string and is parsed to float.

### BB-V3 `[observed]`

| semantic | key | wrapped |
|---|---|---|
| `current_temperature` | `roomTemperature` | no |
| `raw_temperature` | `rawTemperature` | no |
| `target_temperature` | `heatSetpoint` | no |
| `humidity` | `humidity` | no |
| `mode` | `mode` | no |
| `current` | `current` | no |
| `voltage` | `Voltage` | no |
| `duty_cycle` | `dutyCycle` | no |
| `energy` | `energy` | no |
| `power_consumed` | `powerConsumed` | no |
| `core_temperature` | `coreTemperature` | no |
| `connected` | `isConnected` | no |
| `lock` | `Lock` | no |
| `brightness` | `Brightness` | no |
| `firmware` | `fw` | no |

No field is wrapped on BB-V3. Values appear both nested under `reading` and flattened at
the top level; the flattened copy is authoritative and `reading.timestamp` supplies the
staleness timestamp.

### AC-V1 `[observed]`

| semantic | key | wrapped |
|---|---|---|
| `current_temperature` | `CorrectedTemp` | yes |
| `target_temperature` | `SetPoint` | no |
| `humidity` | `Humidity` | yes |
| `mode` | `TstatMode` | no |
| `fan_speed` | `FanSpeed` | no |
| `vertical_swing` | `SwingState` | no |
| `horizontal_swing` | `SwingStateHorizontal` | no |
| `signal_strength` | `Rssi` | no |
| `connected` | `Connected` | no |

AC units report no `Current` or `Voltage`.

### MQTT status field names `[mit-sdk]`

Status messages use shorter keys than REST state. Device classes declare both.

| message | keys |
|---|---|
| `DeviceV1Status` | `MainTemp`, `ThermistorTemp`, `ComboTemp`, `Humidity`, `Current`, `SetPoint` |
| `DeviceV2Status` | `ambTemp`, `dtyCycle`, `hum`, `stpt` |
| `DeviceAcStatus` | `ambTemp`, `hum`, `stpt`, `dtyCycle`, `mode` |

### Unverified models

`BB-V2`, `BB-V2-L`, `INF-V1` and `ST-V1` ship with field maps built from `[mit-sdk]` and
`[inferred]` facts and `VERIFIED = False`. An incorrect key resolves to `None` and the
entity reports unavailable.

| model | fact | source |
|---|---|---|
| `BB-V2-L` | reports no current; power and energy entities absent | `[inferred]` |
| `INF-V1` | floor temperature under `Infloor`; sensor selector `SensorMode`, 0 ambient, 1 floor | `[inferred]` |
| `ST-V1` | drives external HVAC; reports no line current | `[inferred]` |
