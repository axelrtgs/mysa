# 08 — Schedules

A device follows a weekly schedule of events. Home Assistant models scheduling through
its own helpers, so this is `pymysa` surface (spec 06); the integration exposes only the
hold state.

## Hold state `[observed]`

A device with no schedule has no `schedule` section. Configuring one in the app creates
it:

```jsonc
"schedule": { "holding": true, "resolved": true, "nextEvent": 1788170400 }
```

The section is flat: no `desired` and `reported` halves.

| field | meaning |
|---|---|
| `holding` | the device is holding a setting against the schedule |
| `nextEvent` | epoch seconds; when the hold ends, or the next scheduled change |
| `resolved` | accompanies the pair; what it distinguishes is not established |

The two fields together describe three states, each observed by driving the app:

| `holding` | `nextEvent` | state |
|---|---|---|
| `false` | the next scheduled change | following the schedule |
| `true` | absent | holding until changed |
| `true` | a timestamp | holding until that time |

Following the schedule applies the scheduled setting: a BB-V3 moved from
`modes.mode` 0 and `targetHeat.setpoint` 5 to mode 4 and setpoint 16 in the same read.

## Writing the hold `[observed]`

`POST /state/{device_id}/update` with `{"source": 3, "schedule": {"holding": false}}` is
accepted. On an AC-V1 it took: the hold ended and `holding` then read as absent, not as
`false`. Writing `true` back did not recreate it, and the field stayed absent. On a
BB-V1 the same write was accepted and never applied.

A hold is therefore a property of a hold that exists, not a flag on the device: ending
one is a write, and starting one is not — whatever creates a hold carries the setting
being held, which the state document does not.

The harness does not exercise it for that reason (spec 07): the write is real, it
changes the account, and nothing in the state document puts it back.

## Assignment `[observed]`

The `schedule` section exists only while a schedule is assigned. Assigning one creates it
and populates the device record's `Schedule` with the schedule id; deleting the schedule
removes the section, and `holding` and `resolved` read as absent again.

`GET /schedules` returns `Schedules`, an array whose entries carry the `Device` they
belong to. The array comes back in a different order on each read, so an entry is
identified by its contents and not its position.

## Definitions

The container is `ScheduledActions` on a `/schedules` entry, keyed by weekday name:

```jsonc
{"Device": "aabbccddeeff",
 "ScheduledActions": {"Monday": [], "Tuesday": [], ... , "Sunday": []}}
```

An entry carries no id of its own; `Device` identifies it. `[observed]`

What an event inside a day list looks like is not established: every capture has empty
lists, including from devices the app was driving at the time. The state document
carries no event list either, and driving the app while watching every readable surface
did not reveal one.

Reading definitions, and any write path for them, needs the app's own requests observed
rather than its effects: `observe` sees state, and a definition stored behind an endpoint
this project does not call cannot be found by watching state change.

The event encoding below is recorded from elsewhere and is not confirmed against this
account.

## Event encoding `[inferred]`

An event is a pipe-delimited string. The fields, in order, are an enable flag, an index,
a minute of the week counted from Monday 00:00, a mode, and a setpoint, followed by
placeholder fields carrying `%`.

```
1|0|1980|3|18.5|%|%|%|%|%
```

`1980` is Monday 09:00. A `%` is an unset field, and an off event carries `%` where the
setpoint would be.

The encoding is recorded in `dlenski/mysotherm` (GPL-3.0). The field layout is a protocol
fact and is documented here in this project's own words; no text or code is taken from
it. See `NOTICE.md`.
