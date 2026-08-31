# 04 — Capabilities

## Sources

| source | serves |
|---|---|
| `GET /capabilities/{device_id}` | BB-V1-0 and BB-V3-0: a structured declaration |
| `SupportedCaps` on the device record | AC-V1-0: codeset key ids and mode blocks |
| sections present in the state document | whether a control exists at all (spec 02) |

The capability document is authoritative where it is served. It names which fields are
writable and which values they accept, so neither has to be inferred from a refusal.

AC-V1-0 returns 404 `Device ... capabilities not available for this app version`. What
gates it is not established; the request carries the app's user agent and no version
header. AC units therefore fall back to `SupportedCaps`.

## Capability document `[observed]`

```jsonc
{
  "version": "1.0",
  "hardware": {
    "sensors": { "internalTemperatureSensor": true, "proximitySensor": false, ... },
    "communication": { "wifiModule": true, "bluetoothModule": false, "nfcChip": false }
  },
  "features": { ... },
  "system": { ... }
}
```

A leaf under `features` carrying `userControllable` is a setting:

```jsonc
"lockout": { "userControllable": true, "type": "integer", "validValues": [0, 3] }
```

| key | meaning |
|---|---|
| `userControllable` | whether the field may be written |
| `type` | `enum`, `integer`, `float` or `boolean` |
| `validValues` | the accepted set; absent means unconstrained |

A write of a value outside `validValues` is accepted with 200 and never applied. A write
to a field with `userControllable: false` is likewise accepted and ignored.

## Settings by model `[observed]`

| capability path | BB-V1-0 | BB-V3-0 |
|---|---|---|
| `climateControl.mode` | `off`, `heat` | `off`, `heat` |
| `climateControl.heat.setpoint` | 5–30 by 0.5 | 5–30 by 0.5 |
| `climateControl.advancedConfig.baseboardHeating.controlType` | 0, 4, 5, 6, 7 | 0, 1, 2 |
| `climateControl.advancedConfig.baseboardHeating.pid*` | absent | read-only |
| `sensing.temperature.trackingSensor` | `internal` | `internal`, `remote` |
| `sensing.temperature.temperatureOffset` | absent | −5 to 5 by 0.5 |
| `interface.wakeOnApproach` | read-only | writable |
| `interface.lockout` | 0, 3 | 0, 1, 3 |
| `interface.brightness` | unconstrained | unconstrained |
| `interface.unit` | `C`, `F` | `C`, `F` |
| `interface.adaptiveBrightness.intensityMode` | absent | 0, 1, 2, 3 |
| `interface.doCheckmark` | absent | 0, 1 |
| `smart.smartAlerts.*` | writable | writable |
| `smart.powerMonitoring.*` | absent | read-only |
| `smart.diagnostics.errorDetection` | absent | 0, 1, 2 |

`controlType` takes different values on the two models, so a value valid on one is
ignored on the other.

`climateControl.heat.setpoint` is the hardware range. `targetHeat.lockoutMin` and
`lockoutMax` are a narrower user-set limit within it.

## Capability path to state field `[inferred]`

The capability document and the state document use different names. Device classes hold
the mapping; nothing else translates between them.

| capability path | state field |
|---|---|
| `climateControl.mode` | `modes.mode` |
| `climateControl.heat.setpoint` | `targetHeat.setpoint` |
| `climateControl.advancedConfig.baseboardHeating.controlType` | `bbConfig.controlType` |
| `sensing.temperature.trackingSensor` | `tracking.tracking` |
| `sensing.temperature.temperatureOffset` | `tracking.ambientOffset` `[observed]` |
| `interface.wakeOnApproach` | `physicalInterface.wakeOnApproach` |
| `interface.lockout` | `physicalInterface.lockout` |
| `interface.unit` | `physicalInterface.format` |
| `interface.adaptiveBrightness.intensityMode` | `physicalInterface.intensityMode` |
| `interface.doCheckmark` | `physicalInterface.doCheckmark` |

`interface.brightness` has no single state field: the device reports `activeIntensity`
and `idleIntensity`, and the app exposes both separately `[observed]`.

A BB-V1-0 reports `physicalInterface.intensityMode` without declaring it. An undeclared
field is not writable and is not a feature: that model has no adaptive brightness.

The flags under `smart` are capability presence, not settings: `earlyOn` and
`cloudEarlyOn` say which mechanism a model uses for early-on, and the value the user sets
is elsewhere (spec 02).

`smart.smartAlerts.*` is declared per device and set per home (spec 02): the declaration
says the device can take part in an alert, not that it holds one. `smart.diagnostics.
errorDetection` has no state field either. Neither is exercised, because a write has
nothing to read back until the field carrying it is found.

`climateControl.mode` declares names and the state field holds integers. A BB-V1
declaring `off, heat` and applying only 0 and 4 (spec 02) fixes those two values.

## SupportedCaps `[observed]`

Served for AC-V1-0 on the device record.

```jsonc
{
  "tempRange": [16, 30],
  "version": "1.1",
  "keys": [1,2,3,4,5,6,7,8,9,10,11,13,14,47],
  "modes": { "2": { "tempRanges": [[16,30],[25,25]] }, "4": { ... }, "99": { ... } }
}
```

Mode ids here are the AC codeset ids and are not `modes.mode` values. Id 99 is not a
selectable mode. `modes` and `version` are optional: pre-release units omit both.

`keys` is everything the codeset supports. `modifiedKeys` is the subset the user has
enabled through the app's available-modes setting, rewritten in a fresh order on each
change; it is a set (spec 02).

### Codeset-determined controls `[observed]`

An AC controller drives a head unit over infrared. What the codeset can express is what
the unit supports, and it does not follow from the state document: a unit reports
`modes.horizontalSwingState` whether or not its remote has the control, and a write to a
control the codeset cannot express is accepted and never applied.

| control | declared by | fallback |
|---|---|---|
| fan speed | a `fanSpeeds` list in any `modes` entry | key ids 8, 9, 10, 11 |
| vertical swing | a `verticalSwing` list in any `modes` entry | key ids 12, 39, 40, 47 |
| horizontal swing | a `horizontalSwing` list in any `modes` entry | none |

Neither AC-V1-0 on the sample account declares any of those lists; both declare `keys`
only. One reports `modes.horizontalSwingState` and declines every write to it, in every
mode, on a unit whose remote has no horizontal swing — which is the behaviour above and
not a fault. No key id has been tied to horizontal swing, so nothing gates it. `[observed]`

A device that declares no `modes` block and no keys declares nothing, and no control is
gated on it. That is unknown, not empty.

## Exposure

A capability whose option set resolves empty is not declared. Entities and Home
Assistant feature flags follow the declared set.
