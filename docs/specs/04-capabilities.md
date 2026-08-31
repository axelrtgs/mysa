# 04 — Capabilities

## Declaration

Static capabilities are declared per device class:

```python
class BaseboardV1(MysaDevice):
    CAPABILITIES = frozenset({
        Capability.TARGET_TEMPERATURE, Capability.MODE, Capability.LOCK,
        Capability.BRIGHTNESS, Capability.PROXIMITY, Capability.ECO_MODE,
        Capability.CURRENT, Capability.VOLTAGE, Capability.DUTY_CYCLE,
    })
```

AC units extend the static set at runtime from `SupportedCaps`.

## SupportedCaps `[observed]`

```jsonc
{
  "tempRange": [16, 30],
  "version": "1.1",
  "keys": [1,2,3,4,5,6,7,8,9,10,11,13,14,47],
  "modifiedKeys": [1,2,3,7,4,6,5,11,10,9,8,47],
  "modes": { "2": { "tempRanges": [[16,30],[25,25]] }, "4": { ... }, "99": { ... } }
}
```

Mode ids: 2 auto, 3 heat, 4 cool, 5 fan_only, 6 dry. Id 99 is not a selectable mode.

`modes` and `version` are optional. Pre-release AC units omit both; retail units on the
same firmware include them. Both samples are in `docs/samples/`.

## Key ids

| id | meaning | source |
|---|---|---|
| 8, 9, 10, 11 | fan auto, low, medium, high | `[mit-sdk]` |
| 12 | vertical swing toggle | `[inferred]` |
| 39 | vertical swing on | `[inferred]` |
| 40 | vertical swing off | `[inferred]` |
| 47 | vertical swing, toggle-style codesets | `[observed]` |
| 1–7, 13, 14 | unidentified | `[inferred]` |

## Discovery

```
modes = caps.modes or {}

hvac = {OFF} | {MODE_IDS[i] for i in modes if i in MODE_IDS}
if hvac == {OFF} and caps.keys:
    hvac = {OFF, AUTO, HEAT, COOL, FAN_ONLY, DRY}
hvac |= {reported mode}

fan = {FAN_IDS[s] for m in modes.values() for s in m.fanSpeeds}
   or {FAN_IDS[k] for k in caps.keys if k in FAN_KEYS}

vertical = {SWING_IDS[p] for m in modes.values() for p in m.verticalSwing}
        or ({STILL, AUTO} if caps.keys & VSWING_KEYS else {})

horizontal = {HSWING_IDS[p] for m in modes.values() for p in m.horizontalSwing}
```

Horizontal swing has no fallback: absence of `horizontalSwing` means unsupported.

Vertical swing falls back on key presence because a unit reporting a live `SwingState`
supports swing regardless of whether `modes` describes it.

The reported mode is always a member of `hvac`.

Temperature bounds come from `tempRange` when present, otherwise the device class
default.

## Exposure

A capability whose option set resolves empty is not declared. Entities and Home
Assistant feature flags follow the declared set.
