# 02 — Devices

## State document `[observed]`

`/state/batch` returns, per device, a `data` object of named sections.

Shadow sections carry `desired` and `reported`, each with a `timestamp` in epoch
seconds. `reported` is the value in force.

```jsonc
"targetHeat": {
  "desired":  { "timestamp": 1788145825, "setpoint": 5, "lockoutMin": 5, "lockoutMax": 24 },
  "reported": { "timestamp": 1788145823, "setpoint": 5, "lockoutMin": 5, "lockoutMax": 24 }
}
```

`latestTelemetry` is flat and holds the device's own last report:

```jsonc
"latestTelemetry": {
  "isConnected": true,
  "lastConnected": 1788146204,
  "reading": { "roomTemperature": 24.12, "heatSetpoint": 5, "mode": 0, ... }
}
```

`drState` is flat with no shadow pair.

Within a shadow section the two halves need not carry the same fields, and a field in
`reported` with no counterpart in `desired` is usually not writable: the backend keeps no
desired value for it, so the write returns 200 and is dropped. Both AC-V1-0 units report
`modes.unitPower` and neither carries it in `desired`, and writes to it are accepted and
never applied in any mode. `[observed]`

The setpoint lockout pair is the exception. A BB-V1-0 carries `lockoutMin` and
`lockoutMax` in `reported` only, and the app moves both; every model reports a pair
narrower than the range its hardware declares, which is a user setting and not a default.
`[observed]`

A section absent from a device's document is a capability that device does not have.
Nothing reads the model string to decide what a device supports.

A refusal naming a feature is not always a statement about the hardware. A BB-V3 holding
`physicalInterface.wakeOnApproach` at 0 refuses a `woaSensitivity` write with
`"Wake on approach is not supported"`, on a unit whose display does wake on approach and
whose app exposes the setting. The refusal describes the feature being disabled, not
absent. `[observed]`

## Sections `[observed]`

| section | shape | contents |
|---|---|---|
| `identity` | shadow | `model`, `fw`, `serial` |
| `latestTelemetry` | flat | `isConnected`, `lastConnected`, `reading` |
| `modes` | shadow | mode, permitted modes, and on AC units fan, swing, unit power |
| `targetHeat` | shadow | heat setpoint and its lockout range |
| `targetCool` | shadow | cool setpoint and its lockout range |
| `targetAuto` | shadow | auto-mode deadband |
| `physicalInterface` | shadow | display brightness, lockout, temperature format, proximity |
| `power` | shadow | `voltage`, `current`, `wattage`, `dutyCycle`, `fault` |
| `bbConfig` | shadow | heater control type and PID constants |
| `acConfig` | shadow | AC controller configuration |
| `tracking` | shadow | remote sensor selection and offset |
| `matter` | shadow | Matter commissioning state |
| `schedule` | flat | hold state and next event, not the schedule definition; absent until a schedule exists |
| `drState` | flat | demand-response state |
| `cloudFeatures` | shadow | backend feature flags |
| `diagnostics` | shadow | diagnostic counters |
| `telemetry` | shadow | telemetry configuration |

## Sections by model `[observed]`

| section | BB-V1-0 | BB-V3-0 | AC-V1-0 |
|---|---|---|---|
| `identity`, `latestTelemetry`, `modes`, `physicalInterface`, `drState`, `diagnostics` | yes | yes | yes |
| `targetHeat` | yes | yes | yes |
| `bbConfig`, `power` | yes | yes | no |
| `targetCool`, `targetAuto` | no | no | yes |
| `matter`, `tracking`, `cloudFeatures`, `telemetry` | no | yes | no |
| `acConfig` | no | no | one of two units |
| `schedule` | one of two units | no | yes |

Two AC-V1-0 units on the same account differ: one returns `acConfig` and the other does
not. Section presence is per unit, not per model.

`schedule` is per unit for a different reason: it exists while a schedule is assigned to
the device and not otherwise (spec 08). One of the two BB-V1-0 units carries it and the
other does not, on the same firmware. Nothing about the model decides it.

## Device contract

```python
class MysaDevice(ABC):
    MODEL_MATCH: ClassVar[ModelMatch]        # prefix, and suffix where it disambiguates
    FIELDS: ClassVar[FieldMap]               # semantic name -> (section, key)
    CAPABILITIES: ClassVar[frozenset[Capability]]
    VERIFIED: ClassVar[bool]
```

`FIELDS` maps one semantic name to one section and key. Where a device reports the same
value in more than one place, the class names the authoritative one.

`CAPABILITIES` is the static set. Devices whose capabilities depend on runtime data
(AC units, spec 04) override `capabilities()` and extend it.

## Model registry

| model | product | verified |
|---|---|---|
| `BB-V1-*` | Baseboard V1 | yes |
| `BB-V2-*` (no `-L`) | Baseboard V2 | no |
| `BB-V2-*-L` | Baseboard V2 Lite | no |
| `BB-V3-*` | Baseboard V3 | yes |
| `AC-V1-*` | Mini-split controller | yes |
| `INF-V1-*` | In-floor | no |
| `ST-V1-*` | Central HVAC | no |

Matching is on prefix; the `-L` suffix is matched explicitly.

Unverified models carry `VERIFIED = False`. An incorrect mapping resolves to `None` and
the entity reports unavailable.

## Semantic fields

A semantic name is what the integration reads. Each carries a criticality, which is a
property of the role rather than of any model: a thermostat that cannot report its
target temperature is broken whatever it is.

| criticality | meaning | names |
|---|---|---|
| `critical` | the climate entity cannot function | `current_temperature`, `target_temperature`, `mode`, `connected` |
| `important` | a control or measurement is lost; the device still works | `humidity`, `min_setpoint`, `max_setpoint`, `fan_speed`, `vertical_swing`, `horizontal_swing`, `lock`, `brightness`, `temperature_format`, `current`, `voltage`, `wattage`, `energy`, `power_consumed` |
| `informational` | read but not surfaced as an entity | everything else mapped |

A section or key present in the document but named by no device class is not read at all.

## Mode `[observed]`

`modes.mode` is the mode in force. Its values are not the AC codeset mode ids in spec 04;
they are a separate enum, established only where a device has been seen holding one.

| value | meaning |
|---|---|
| 0 | off |
| 1 | auto |
| 3 | cool |
| 4 | heat |
| 7 | fan only |
| 8 | dry |

Each named by selecting it in the app on an AC-V1-0 and reading the value back. That is
the only model offering all six; a baseboard offers off and heat.

Writing `2` is refused on every model with `body/modes/mode must be equal to constant`.
No device has produced 5 or 6.

Which values a device applies is per model, and a value the schema accepts is not a value
the hardware takes:

| model | applies |
|---|---|
| BB-V1-0 | 0, 4 |
| BB-V3-0 | 0, 1, 3, 4, 5, 6 |
| AC-V1-0 | 0, 1, 3, 4, 7, 8 |

A BB-V3-0 accepting values its hardware cannot act on is not the same as supporting them;
what 1, 3, 5 and 6 do on a baseboard is not established.

`modes.lockoutModes` is a mask of the modes a device permits, reported as 255 on BB-V3.
Its bit order is not established. A BB-V3 permitting every mode is consistent with it
applying every mode above.

## Fan and swing `[observed]`

Named the same way on an AC-V1-0.

| field | values |
|---|---|
| `modes.fan_mode` | 0 auto, 1 low, 2 medium, 3 high |
| `modes.verticalSwingState` | 1 off, 2 on |

## Available modes `[observed]`

`SupportedCaps.modifiedKeys` on the device record is the set of modes the user has
enabled, as codeset key ids. Turning a mode off in the app removes its keys; turning it
back on restores them. The array is rewritten in a different order each time, so it is a
set and its order carries nothing.

Disabling heat removes two keys, and disabling dry or fan-only removes one each.

`SupportedCaps.keys` is everything the codeset supports and does not change.

## Mirrored settings `[observed]`

Two settings appear in both the state document and the device record, and the app moves
both:

| device record | state |
|---|---|
| `ButtonState` (`Locked` / `Unlocked`) | `physicalInterface.lockout` |
| `IsThermostatic` (boolean) | `modes.isThermostatic` |

`IsThermostatic` is Climate+ in the app.

## Heater control type `[observed]`

`bbConfig.controlType` selects the heater a baseboard drives. The value set is per model
(spec 04) and so are the meanings.

BB-V1-0, each named by changing the heater type in the app and reading the value back:

| value | heater |
|---|---|
| 0 | baseboard |
| 4 | radiant |
| 5 | fan forced, short cycle |
| 6 | fan forced, medium cycle |
| 7 | fan forced, long cycle |

BB-V3-0, named the same way:

| value | heater |
|---|---|
| 0 | baseboard |
| 1 | fan forced |
| 2 | radiant |

The two models share only `0`. On a BB-V1-0 the value 1 is not valid at all, and 4 is
radiant where a BB-V3-0 has no 4.

## Settings on the device record `[observed]`

Not every setting is in the state document. The device record from `/devices` carries
some of its own.

| field | meaning |
|---|---|
| `schedGlobalOffset` | early-on on a BB-V1-0; 0 off, 1 on |
| `Schedule` | the id of the schedule assigned to the device, absent when there is none |

## Early-on `[observed]`

The app calls it early-on on both baseboard models and it is stored differently on each.

| model | field | shape |
|---|---|---|
| BB-V1-0 | `schedGlobalOffset` on the device record | 0 or 1 |
| BB-V3-0 | `cloudFeatures.cloudEarlyOn` in the state document | `{"enabled": bool}` |

The capability document distinguishes them: a BB-V1-0 declares `smart.earlyOn` true and
`smart.cloudEarlyOn` false. They are the same setting to the user and not the same
mechanism, so a device class maps whichever its model carries.

## Home-level settings

Smart alerts are not a device setting. The app places them under the home, where an alert
is enabled once and the thermostats it reads from are selected. Each device's capability
document declares `smart.smartAlerts.*`, which says the device can take part, not that it
holds the setting.

Toggling one moves nothing in the state document, the device record, `/homes`, a
per-home record, `/schedules` or `/users` `[observed]`. Their storage is not established
and is not on any surface this project reads. Finding it needs the app's own requests
observed, not its effects.

## Dependent settings `[inferred]`

A setting that configures a feature is writable only while that feature is enabled.

| setting | enabled by |
|---|---|
| `physicalInterface.woaSensitivity` | `physicalInterface.wakeOnApproach` = 1 |
| `physicalInterface.darkRoomLevel` | `physicalInterface.intensityMode` = 1 |
| `physicalInterface.brightRoomLevel` | `physicalInterface.intensityMode` = 1 |

`intensityMode` is adaptive brightness; a BB-V3 reports 1 with it enabled in the app.

## Keypad lockout `[observed]`

`physicalInterface.lockout` is not a boolean.

| value | meaning | models |
|---|---|---|
| 0 | unlocked | all |
| 1 | limited to the lockout range | BB-V3-0 |
| 3 | full | all |

Under `1` the device accepts setpoints only within `targetHeat.lockoutMin` and
`lockoutMax`, which is what those two fields bound. Under `3` the keypad is inert.

An AC-V1-0 accepts a write of `1` and never applies it, in every mode tried. The value
is in the enum because the field carries it; it is not a state that model reaches.

## Display brightness `[observed]`

The capability document declares one `interface.brightness`; the device reports two
fields and the app exposes both. `physicalInterface.activeIntensity` is the display while
in use and `idleIntensity` is at rest.

A BB-V1-0 reports `physicalInterface.intensityMode`, accepts a write of 1 and reads it
back, and has no adaptive brightness: the capability document does not declare the field
and the model carries no ambient light sensor. Neither reporting a field nor writing one
successfully makes it a feature (spec 03).

`physicalInterface.doCheckmark` is a trigger, not a setting. A BB-V3-0 holds `desired`
1 across runs while `reported` stays 0: the device shows the checkmark and keeps nothing.
Anything that confirms a write by reading it back will report it as never applied.

A BB-V3-0 accepts `intensityMode` 0, 1, 2 and 3. Only 0 (fixed) and 1 (adaptive) are
named, from watching the app; 2 and 3 are values the device takes and nothing has been
seen to select.

## Electrical units

`power.voltage` is volts and `power.wattage` is watts. `power.current` is milliamps: a
BB-V3-0 reporting `{"voltage": 240, "current": 12458, "wattage": 2989}` is consistent
only at that scale, since 12.458 A at 240 V is 2990 W. `[inferred]`

Both BB-V1-0 captures report `current` and `wattage` as 0, so nothing fixes the scale on
that model. It is read as milliamps because the section has the same shape and no capture
contradicts it, not because it has been seen.

`latestTelemetry.reading.energy` and `powerConsumed` have no established unit: every
capture reports 0 for both. What the integration declares for them, and why, is in
spec 05.

## Value shapes

A field whose values are drawn from a fixed set or a fixed range carries a declared
shape. A value outside its shape is reported (spec 07): either the mapping is wrong or
the device does something not yet described.

| kind | declaration |
|---|---|
| `enum` | the permitted values |
| `range` | inclusive bounds |
| `boolean` | JSON `true` or `false` |
| `bounded` | bounds read from named fields in the same section |

| section | field | shape | source |
|---|---|---|---|
| `latestTelemetry` | `isConnected` | boolean | `[observed]` |
| `modes` | `mode` | enum 0, 1, 3, 4, 7, 8 | `[observed]` |
| `modes` | `fan_mode` | enum 0–3 | `[inferred]` |
| `modes` | `verticalSwingState` | enum 1–2 | `[inferred]` |
| `modes` | `horizontalSwingState` | enum 1–2 | `[inferred]` |
| `modes` | `unitPower` | enum 1–2 | `[inferred]` |
| `modes` | `isThermostatic` | enum 0–1 | `[inferred]` |
| `physicalInterface` | `format` | enum `"C"`, `"F"` | `[inferred]` |
| `physicalInterface` | `lockout` | enum 0, 1, 3 | `[observed]` |
| `physicalInterface` | `wakeOnApproach` | enum 0–1 | `[inferred]` |
| `physicalInterface` | `activeIntensity` | range 0–100 | `[inferred]` |
| `physicalInterface` | `idleIntensity` | range 0–100 | `[inferred]` |
| `physicalInterface` | `woaSensitivity` | range 0–100 | `[inferred]` |
| `physicalInterface` | `intensityMode` | enum 0–3 | `[observed]` |
| `physicalInterface` | `doCheckmark` | enum 0–1 | `[observed]` |
| `power` | `dutyCycle` | range 0–100 | `[inferred]` |
| `power` | `fault` | enum 0–5, from the BB-V3 capability document | `[observed]` |
| `targetHeat` | `setpoint` | bounded by `lockoutMin`, `lockoutMax` | `[observed]` |
| `targetCool` | `setpoint` | bounded by `lockoutMin`, `lockoutMax` | `[inferred]` |
| `latestTelemetry.reading` | `humidity` | range 0–100 | `[inferred]` |
| `latestTelemetry.reading` | `dutyCycle` | range 0–100 | `[inferred]` |
| `tracking` | `ambientOffset` | range −5 to 5 | `[observed]` |

Unshaped, and never checked: identifiers (`deviceId`, `serial`), versions (`model`,
`fw`), timestamps, measured quantities (temperatures, current, voltage, wattage,
energy), tuning constants (`bbConfig`), and display thresholds whose units are unknown
(`darkRoomLevel`, `brightRoomLevel`, reported as 5 and 500, so not percentages).

Declaring a shape for a field whose real range is unknown produces false reports. A
field is left unshaped until its shape is established.

## Homes `[observed]`

`GET /homes` returns `Homes`, whose entries carry `Id`, `Name`, `Owner`, `ERate`, and
nested `Address`, `AllowedUsers` and `Zones`. `ERate` is the account's electricity rate
per kilowatt hour, served as a string (`"0.0616"`); it is the only value in the payload
a device reads, and it is what an energy cost is derived from. A device's `Home` names
the entry it belongs to.

## Field maps

Setpoint and mode are read from the shadow sections. Temperature, humidity and
electrical values are read from `latestTelemetry.reading`.

A write moves the shadow section immediately; `latestTelemetry.reading` follows on the
device's own reporting interval. Reading a setpoint from telemetry returns a stale value
for as long as that interval.

### BB-V1-0 `[observed]`

| semantic | source |
|---|---|
| `connected` | `latestTelemetry.isConnected` |
| `current_temperature` | `latestTelemetry.reading.roomTemperature` |
| `raw_temperature` | `latestTelemetry.reading.rawTemperature` |
| `core_temperature` | `latestTelemetry.reading.coreTemperature` |
| `humidity` | `latestTelemetry.reading.humidity` |
| `signal_strength` | `latestTelemetry.reading.rssi` |
| `power_consumed` | `latestTelemetry.reading.powerConsumed` |
| `on_time` | `latestTelemetry.reading.onTime` |
| `target_temperature` | `targetHeat.reported.setpoint` |
| `min_setpoint` / `max_setpoint` | `targetHeat.reported.lockoutMin` / `lockoutMax` |
| `mode` | `modes.reported.mode` |
| `current` | `power.reported.current` |
| `voltage` | `power.reported.voltage` |
| `wattage` | `power.reported.wattage` |
| `duty_cycle` | `power.reported.dutyCycle` |
| `lock` | `physicalInterface.reported.lockout` |
| `temperature_format` | `physicalInterface.reported.format` |
| `active_brightness` / `idle_brightness` | `physicalInterface.reported.activeIntensity` / `idleIntensity` |
| `brightness_mode` | `physicalInterface.reported.intensityMode` |
| `proximity` | `physicalInterface.reported.wakeOnApproach` |
| `heater_type` | `bbConfig.reported.controlType` |
| `firmware` | `identity.reported.fw` |
| `family` | `identity.reported.family` |

A BB-V1-0 reports no `serial`: its `identity` carries `family`, `fw` and `model` only.
`brightness_mode` and `proximity` are reported and not writable — the capability document
declares `interface.wakeOnApproach` read-only and does not declare `intensityMode` at all
(spec 04). A field being readable is not a control.

### BB-V3-0 `[observed]`

As BB-V1-0, with `serial` from `identity.reported.serial`, without `signal_strength` —
its telemetry reading carries no `rssi` — and additionally:

| semantic | source |
|---|---|
| `secondary_raw_temperature` | `latestTelemetry.reading.secondaryRawTemperature` |
| `energy` | `latestTelemetry.reading.energy` |
| `fault` | `power.reported.fault` |
| `remote_temperature` | `tracking.reported.remoteTemperature` |
| `tracking_mode` | `tracking.reported.tracking` |
| `ambient_offset` | `tracking.reported.ambientOffset` |
| `proximity_sensitivity` | `physicalInterface.reported.woaSensitivity` |
| `early_on` | `cloudFeatures.cloudEarlyOn.enabled` |

### AC-V1-0 `[observed]`

| semantic | source |
|---|---|
| `connected` | `latestTelemetry.isConnected` |
| `current_temperature` | `latestTelemetry.reading.roomTemperature` |
| `raw_temperature` | `latestTelemetry.reading.rawTemperature` |
| `humidity` | `latestTelemetry.reading.humidity` |
| `signal_strength` | `latestTelemetry.reading.rssi` |
| `on_time` | `latestTelemetry.reading.onTime` |
| `target_temperature` | `targetHeat.reported.setpoint` |
| `target_temperature_cool` | `targetCool.reported.setpoint` |
| `target_temperature_auto` | `targetAuto.reported.setpoint` |
| `min_setpoint` / `max_setpoint` | `targetHeat.reported.lockoutMin` / `lockoutMax` |
| `mode` | `modes.reported.mode` |
| `fan_speed` | `modes.reported.fan_mode` |
| `vertical_swing` | `modes.reported.verticalSwingState` |
| `horizontal_swing` | `modes.reported.horizontalSwingState` |
| `unit_power` | `modes.reported.unitPower` |
| `thermostatic` | `modes.reported.isThermostatic` |
| `lock` | `physicalInterface.reported.lockout` |
| `temperature_format` | `physicalInterface.reported.format` |
| `active_brightness` / `idle_brightness` | `physicalInterface.reported.activeIntensity` / `idleIntensity` |
| `firmware` | `identity.reported.fw` |
| `family` | `identity.reported.family` |

AC units report no `power` section, no `serial`, and no `energy`. The telemetry reading
carries `voltage`, `instantLoad` and `maxCurrent`, and none of them is mapped: the unit
is an infrared blaster and measures nothing about the head unit it drives, so its 240 V
describes the controller's own supply and its load is always zero. `unit_power` is
reported and not writable (spec 03).

Only one unit of the two carries `modes.horizontalSwingState` and `acConfig` at all;
the field maps name every field the model has been seen to report, and a device that does
not report one reads `None` for it.
