# 05 — Telemetry

## Extraction

A value is read through the device's `FIELDS` map. Keys listed in `WRAPPED_FIELDS` are
unwrapped from `{"v": value, "t": timestamp}`; all others are read directly. A key absent
from the payload yields `None`.

`None` propagates to the entity as unavailable. No default is substituted.

## Power and energy

Derived only from measured values:

```
power_w = voltage * current
```

Duty cycle is a separate diagnostic percentage and is not a factor in instantaneous
power.

Where a device reports `energy` or `powerConsumed` directly, the device value is used in
preference to any derivation.

Devices that do not report current expose no power or energy entities.

| model | current reported | power / energy entities |
|---|---|---|
| BB-V1 | yes `[observed]` | yes |
| BB-V3 | yes `[observed]` | yes |
| BB-V2 | yes `[mit-sdk]` | yes |
| AC-V1 | no `[observed]` | no |
| BB-V2-L | no `[inferred]` | no |
| ST-V1 | no `[inferred]` | no |

Estimation from configured wattage and duty cycle is not implemented.

## Cost

`electricity_rate` from the device record is exposed as a diagnostic sensor. No cost
sensor is created; energy is supplied to Home Assistant, which applies its own rate.

## Diagnostics

Enabled by default where reported: signal strength, duty cycle, current, voltage,
firmware, connection state.

Disabled by default: free heap, free PSRAM, boot count, boot time, timezone, fault test,
secure boot and encryption flags.
