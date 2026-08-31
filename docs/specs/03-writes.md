# 03 — Writes

## Request `[observed]`

```
POST https://mysa-backend.mysa.cloud/state/{device_id}/update

{"source": 3, "targetHeat": {"setpoint": 21}}
```

One shadow section per request. `source` identifies the caller and is present on every
write; value 3 is what the app sends.

A successful write returns:

```jsonc
{"message": "Successfully updated state for device <device id>"}
```

## Refusals `[observed]`

Two shapes, from two different checks. Both are 400 and both change nothing.

Schema validation names the field path and the constraint:

```jsonc
{"statusCode": 400, "code": "FST_ERR_VALIDATION", "error": "Bad Request",
 "message": "body/targetHeat/setpoint must be >= 5"}
```

```jsonc
{"statusCode": 400, "code": "FST_ERR_VALIDATION", "error": "Bad Request",
 "message": "body/modes/mode must be equal to constant"}
```

Capability refusal names the feature in a list, with no `code`:

```jsonc
{"error": "Failed to validate request body",
 "message": ["Wake on approach is not supported"]}
```

A capability refusal is the backend stating the device does not have the feature, even
where the field is present in its state document. It is a fact about the device, not a
malformed request.

## Accepted and not applied `[observed]`

A write can return 200 and never appear in `reported`. The backend accepted it; the
device did not take it.

On an AC-V1 holding `modes.mode` 3, a `targetCool.setpoint` write applies and a
`targetHeat.setpoint` write does not. A device carrying both `targetHeat` and
`targetCool` applies the one its current mode selects. A device carrying only
`targetHeat` applies it in any mode, including 0.

Bounds are per device and are read from the same section: `targetHeat.lockoutMin` and
`lockoutMax` bound `targetHeat.setpoint`.

## Applied and still not a feature `[observed]`

A write can be accepted, appear in `reported`, survive a restore - and drive nothing. A
BB-V1-0 takes `physicalInterface.intensityMode` 1 and reads it back, and that model has
no ambient light sensor to be adaptive with: the sensor arrives with BB-V2 and proximity
with BB-V3.

So a confirmed write is evidence about the field, not about the feature behind it. What
the hardware has is what the capability document says it has, and where the two disagree
the document wins. A control offered on the strength of a write landing is a control that
reports its own setting back to the user and does nothing else.

## Units `[observed]`

Setpoints are degrees Celsius in steps of 0.5: a BB declares
`climateControl.heat.setpoint` valid at 5, 5.5, 6 … 30 (spec 04). Lockout bounds are
whole degrees. A device reporting `{"setpoint": 5, "lockoutMin": 5, "lockoutMax": 24}` is
bounded at 5 and 24 within that scale.

## Confirmation `[observed]`

A write is confirmed by reading `/state/batch` and finding the value in the section's
`reported` half. Observed round trip is under one second.

Timestamps do not indicate what changed: a write to one section also advances the
`timestamp` of sibling sections whose contents are unchanged.

## Fields

| write | section | field | encoding | source |
|---|---|---|---|---|
| heat setpoint | `targetHeat` | `setpoint` | 5–30 by 0.5, inside the device's lockout range | `[observed]` |
| cool setpoint | `targetCool` | `setpoint` | degrees | `[inferred]` |
| setpoint limits | `targetHeat` / `targetCool` | `lockoutMin`, `lockoutMax` | degrees | `[inferred]` |
| mode | `modes` | `mode` | mode id | `[inferred]` |
| fan speed | `modes` | `fan_mode` | fan id | `[inferred]` |
| vertical swing | `modes` | `verticalSwingState` | swing id | `[inferred]` |
| horizontal swing | `modes` | `horizontalSwingState` | position id | `[inferred]` |
| unit power | `modes` | `unitPower` | not writable: reported with no desired half (spec 02) | `[observed]` |
| auto setpoint | `targetAuto` | `setpoint` | degrees | `[observed]` |
| lock | `physicalInterface` | `lockout` | 0 or 3; BB-V3 also 1 | `[observed]` |
| proximity | `physicalInterface` | `wakeOnApproach` | 0 or 1; read-only on BB-V1 | `[observed]` |
| proximity sensitivity | `physicalInterface` | `woaSensitivity` | 0–100 | `[inferred]` |
| active brightness | `physicalInterface` | `activeIntensity` | 0–100 | `[inferred]` |
| idle brightness | `physicalInterface` | `idleIntensity` | 0–100 | `[inferred]` |
| temperature format | `physicalInterface` | `format` | `"C"` or `"F"` | `[inferred]` |
| brightness mode | `physicalInterface` | `intensityMode` | 0, 1, 2, 3; BB-V3 only | `[observed]` |
| dark room threshold | `physicalInterface` | `darkRoomLevel` | light level; requires `intensityMode` 1 | `[observed]` |
| bright room threshold | `physicalInterface` | `brightRoomLevel` | light level; requires `intensityMode` 1 | `[observed]` |
| confirmation tick | `physicalInterface` | `doCheckmark` | 0 or 1; BB-V3 only | `[observed]` |
| permitted modes | `modes` | `lockoutModes` | mask | `[inferred]` |
| heater control type | `bbConfig` | `controlType` | BB-V1 0, 4, 5, 6, 7; BB-V3 0, 1, 2 | `[observed]` |
| sensor tracking | `tracking` | `tracking` | integer; the capability document names the values `internal` and `remote`, and which number is which is not established | `[observed]` |
| ambient offset | `tracking` | `ambientOffset` | −5 to 5 by 0.5; BB-V3 only | `[observed]` |
| remote sensor timeout | `tracking` | `remoteTTL` | seconds | `[inferred]` |
| early on | `cloudFeatures` | `cloudEarlyOn.enabled` | boolean | `[inferred]` |
| schedule hold | `schedule` | `holding` | `false` ends a hold; nothing starts one (spec 08) | `[observed]` |

Value sets come from the capability document (spec 04) where a device serves one. A value
outside the declared set is accepted with 200 and never applied, which is how
`physicalInterface.lockout` and `bbConfig.controlType` appeared to be broken write paths:
1 is not a valid value for either on a BB-V1.

A write marked *accepted, never applied* returned 200 with a value the device declares as
valid, and was not taken.

A write marked `[inferred]` has a known field name and value shape read from device
state, and no confirmed write. `exercise` (spec 07) promotes one to `[observed]` by
writing it, reading it back, and restoring it.

## Encoding

A device constructs only writes for sections and fields present in its own state
document. `MysaDevice.write` raises `UnsupportedCommand` for anything else. Callers check
`device.capabilities()` first.
