# 05 — Telemetry

## Extraction

A value is read through the device's `FIELDS` map, which names a section and a key
(spec 02). A key absent from the document yields `None`.

`None` propagates to the entity as unavailable. No default is substituted.

A field that resolves to `None` is logged once per device at the severity of its
criticality (spec 02): `critical` at error, `important` at warning, `informational` at
debug. The entity is unavailable in every case; the severity distinguishes a broken
thermostat from a missing convenience.

## Reading fields `[observed]`

`latestTelemetry.reading` is the device's own last report.

| field | models |
|---|---|
| `roomTemperature`, `rawTemperature`, `humidity`, `mode`, `heatSetpoint` | all |
| `coreTemperature`, `dutyCycle`, `onTime`, `powerConsumed`, `current` | BB-V1, BB-V3 |
| `energy`, `secondaryRawTemperature`, `configuredTracking`, `remoteTemperature` | BB-V3 |
| `instantLoad`, `maxCurrent`, `voltage`, `wattage`, `freeHeap`, `rssi` | BB-V1 |
| `coolSetpoint`, `fan`, `swing`, `devicePower`, `effectiveSetpoint` | AC-V1 |
| `thermostatMode`, `isInThermostaticMode`, `thermostaticOffset`, `delta`, `source` | AC-V1 |
| `vaDirection`, `vaDrift`, `vaIsSteadyState`, `vaRateOfChange`, `vaSteadyStateTemp` | AC-V1 |

`reading.timestamp` supplies the staleness timestamp.

Every observed reading carries `timestampEstimated: true`. What the flag qualifies is
not established. Until it is, `energy` and `powerConsumed` are exposed as reported by
the device and no value is derived from them.

## Power and energy

Derived only from measured values:

```
power_w = voltage * current
```

Duty cycle is a separate diagnostic percentage and is not a factor in instantaneous
power.

Where a device reports `wattage` from a section that moves, that value is used in
preference to the derivation. A BB-V3-0's section does not move (spec 02), so that model
derives - which is what its own app does: it is the only model whose app shows a live
wattage, and it reads zero with the heater off.

Devices that do not report current expose no power or energy entities.

| model | current reported | power / energy entities |
|---|---|---|
| BB-V1 | yes `[observed]` | yes |
| BB-V3 | yes `[observed]` | yes |
| BB-V2 | unknown | on report |
| AC-V1 | no `[observed]` | no |
| BB-V2-L | no `[inferred]` | no |
| ST-V1 | no `[inferred]` | no |

Estimation from configured wattage and duty cycle is not implemented.

## Units

`current`, `voltage` and `wattage` carry established units (spec 02): milliamps, volts
and watts.

`energy` is exposed as kilowatt hours. `[inferred]` No capture reports a non-zero value,
so the scale is taken from the app rather than read back from a device, and declaring it
is what puts the value on Home Assistant's energy dashboard (spec 06). A capture with a
non-zero `energy` settles it: compare its delta against `wattage` over the same interval
and correct the entity if the field turns out to be watt hours.

`powerConsumed` is exposed with no unit and no device class: nothing establishes one,
and nothing downstream needs one.

## Cost

`electricity_rate` from the home record is exposed as a diagnostic sensor. No cost
sensor is created; energy is supplied to Home Assistant, which applies its own rate.

## Diagnostics

Enabled by default where reported: signal strength, duty cycle, current, voltage,
firmware, connection state.

Disabled by default: free heap, boot count, PID constants, fault flags.
