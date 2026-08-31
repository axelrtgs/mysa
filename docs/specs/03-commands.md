# 03 — Commands

## Envelope `[mit-sdk]`

```jsonc
{
  "msg":  "CHANGE_DEVICE_STATE",
  "id":   1788129884123,
  "time": 1788129884,
  "ver":  "1.0",
  "src":  { "ref": "<username>", "type": 100 },
  "dest": { "ref": "<device id>", "type": 1 },
  "resp": 2,
  "body": { "ver": 1, "type": <device COMMAND_TYPE>, "cmd": [ { "tm": -1, ... } ] }
}
```

`id` is epoch milliseconds and correlates the response. `time` is epoch seconds.
`tm: -1` applies immediately. Multiple fields may be set in one `cmd` entry.

## Fields

| field | meaning | encoding | source |
|---|---|---|---|
| `sp` | setpoint | °C | `[mit-sdk]` |
| `md` | mode | 1 off, 2 auto, 3 heat, 4 cool, 5 fan_only, 6 dry | `[mit-sdk]` |
| `fn` | fan speed | 1 auto, 3 low, 5 medium, 7 high, 8 max | `[mit-sdk]` |
| `ss` | vertical swing | 1 still, 2 auto | `[observed]` |
| `ssh` | horizontal swing | position id | `[inferred]` |

Fan speed values are non-contiguous and are not treated as ordinal.

## Command set

| command | capability | fields |
|---|---|---|
| set setpoint | `TARGET_TEMPERATURE` | `sp` |
| set mode | `MODE` | `md` |
| set fan speed | `FAN_SPEED` | `fn` |
| set vertical swing | `VERTICAL_SWING` | `ss` |
| set horizontal swing | `HORIZONTAL_SWING` | `ssh` |
| set lock | `LOCK` | `[inferred]` |
| set brightness range | `BRIGHTNESS` | `[inferred]` |
| set auto brightness | `AUTO_BRIGHTNESS` | `[inferred]` |
| set proximity | `PROXIMITY` | `[inferred]` |
| set eco mode | `ECO_MODE` | `[inferred]` |
| set temperature format | `TEMPERATURE_FORMAT` | `[inferred]` |
| set setpoint limits | `SETPOINT_LIMITS` | `[inferred]` |
| set sensor mode | `SENSOR_MODE` | `[inferred]` |

Commands marked `[inferred]` are read from state but their write encoding is
unconfirmed. They are implemented once a capture from the debug harness (spec 07)
confirms the field name and value encoding.

## Encoding

A device encodes only commands whose capability it declares. `MysaDevice.encode` raises
`UnsupportedCommand` for anything else. Callers check `device.capabilities()` first.
