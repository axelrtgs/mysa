# 07 — Debug harness

A tool shipped with `pymysa` that records what an account's devices report and what they
accept. Its outputs are the evidence behind spec 02 and spec 03, and the route by which a
model nobody owns gains support.

## Invocation

```
python -m pymysa.debug inspect  [--device <id>]
python -m pymysa.debug exercise [--device <id>] [--all] [--yes]
python -m pymysa.debug observe  [--device <id>]
python -m pymysa.debug process
```

Credentials come from a cached session, then `MYSA_USERNAME` / `MYSA_PASSWORD`, then an
interactive prompt. They are never written to a sample.

The session cache holds the Cognito refresh token and is written `0600` to
`$XDG_CACHE_HOME/pymysa/session.json` (default `~/.cache/pymysa/session.json`), outside
any repository. The password is not stored. `--login` bypasses the cache; `--session`
relocates it.

## inspect

Reads every endpoint the account exposes — `/devices`, `/state/batch`,
`/capabilities/{id}`, `/devices/update_available/{id}`, `/homes` — and reports, per
device: model, firmware, connection state, every section, and every field in each
section. An endpoint that errors is recorded with its error rather than omitted.

### Field differences

A capture is compared against the committed sample **for that unit**,
`docs/samples/<model>/read/<device alias>.json`. Units of one model differ - two AC-V1-0
on one account, one carrying `acConfig` and `horizontalSwingState` and the other not - so
a baseline unioned across a model reports one unit's fields as missing from another.

**New** — present in the capture, absent from that unit's sample. A firmware or backend
change surfaces rather than being ignored. A unit with no committed sample has no
baseline: every field is new and nothing is missing.

**Differs from other units** — present on another unit of the same model and absent here,
or the reverse. Always informational, never an error. This is how the pre-release and
retail AC-V1-0 split was found.

**Missing** — present in that unit's own sample, absent from the capture. Severity comes
from the semantic name the device class maps that field to (spec 02):

| severity | condition |
|---|---|
| `error` | the field backs a `critical` semantic name |
| `warning` | the field backs an `important` semantic name |
| `info` | the field is mapped `informational`, or is not read at all |

```
ERROR    BB-V1-0  targetHeat.setpoint absent      (target_temperature)
WARNING  BB-V1-0  physicalInterface.lockout absent (lock)
INFO     BB-V1-0  bbConfig.pidFastKd absent        (not read)
```

**Unexpected value** — a field whose value falls outside its declared shape (spec 02).
Severity follows the same criticality mapping, so a mode outside its enum is an error
while a brightness outside 0–100 is a warning.

```
ERROR    AC-V1-0  modes.mode = 9 (expected one of 0, 1, 2, 3, 4, 5, 6)
WARNING  BB-V1-0  physicalInterface.activeIntensity = 120 (expected 0-100)
ERROR    BB-V1-0  targetHeat.setpoint = 30 (expected 5-24)
```

Only shaped fields are checked. A field with no declared shape produces no report,
whatever its value.

A difference found on several units is reported once, with the count.

An `error` sets a non-zero exit status. A `warning` or `info` does not.

## exercise

For each device, builds a plan from that device's own state document: every parameter in
the catalogue whose section and field the device reports. Nothing is attempted on a
device that does not report it.

A parameter that configures a feature is written only while that feature is enabled
(spec 02). Where the enabling field is off, the harness turns it on for the trial and
puts both back afterwards. Without that, the setting is refused and the refusal reads as
a missing capability.

Whether it is off is read at the moment of the write, not when the plan was built.
Restores are deferred, so a trial on the enabling field itself can leave it somewhere
else: `intensityMode` is found at 1, which is what `darkRoomLevel` requires, and its own
trials leave it at 3.

The sweep restores dependent settings before the fields they depend on, for the same
reason: switching `wakeOnApproach` off first has the device refuse the write that puts
`woaSensitivity` back.

A parameter whose capability document declares its values as names that no map
translates (spec 02) is not attempted either, and is listed as skipped with the names it
declares. `sensing.temperature.trackingSensor` declares `internal` and `remote` for a
field holding `0`; written back as a name the schema refuses it, which reads as a broken
write path rather than a meaning nobody has established yet.

A field the device reports with no counterpart in the section's `desired` half is not
attempted, and is listed as skipped as reported-only. The backend holds no desired value
for it, so the write is accepted and dropped whatever the mode, and the mode retry below
would otherwise spend a pass per mode establishing that.

A parameter that cannot be confirmed by reading it back is not in the catalogue at all:
`physicalInterface.doCheckmark` triggers a display animation and is never held (spec 02),
so every run would report it as accepted and not applied.

A write with no way back is not attempted at all. `schedule.holding` ends a hold the
account had, and no write recreates it (spec 08); a harness that cannot restore what it
changed has no business writing it.

A parameter gated on a control the device's codeset does not declare (spec 04) is not
attempted, and is listed as skipped with the control that gates it. Writing to a control
a remote cannot express produces an accepted-and-ignored write, which is noise rather
than evidence.

A parameter drawn from a fixed set yields one trial per value in that set other than
the current one, so every value is written from whatever state the device was found in.
A device found off is switched on; a device found on is switched off and back. A numeric
parameter yields one trial, a step away from its current value.

Each trial is:

1. write the value
2. read `/state/batch` until `reported` carries it, or the timeout lapses

Originals are not written back between trials. A restore is a second write and a second
confirmation, and the sweep below does it once per device instead of once per trial.

A trial therefore runs in the state its predecessors left. Parameters that change how
other parameters behave — mode, and unit power — are exercised last for that reason, so
everything else runs in the state the device was found in. A parameter that enables
another (spec 02) is the exception: it is switched back immediately, because the next
trial's original value was recorded with it off.

| outcome | meaning | fails the run |
|---|---|---|
| `passed` | written, confirmed, restored | no |
| `unsupported` | the backend named the feature as unsupported | no |
| `not applied` | accepted, never read back; the device declined it | no |
| `rejected` | schema refusal; the constraint is recorded | no |
| `not restored` | the original value could not be written back | yes |
| `error` | the request failed for any other reason | yes |

The two refusal shapes in spec 03 separate `unsupported` from `rejected`. Neither is a
defect in the harness or the device: a schema constraint and a capability refusal are
both facts worth recording, and a run made entirely of them is a successful run.

Only a device left changed, or a request that failed for a reason the harness cannot
classify, fails the run. A parameter that a device declines is described, not panicked
over.

### Mode-scoped parameters

A write accepted and not applied is often a parameter the device's current mode does not
select — an AC in cool applies `targetCool.setpoint` and ignores `targetHeat.setpoint`.

After the mode trials, every parameter that came back `not applied` is retried once under
each mode that was successfully applied during the run. The modes in which it applies are
recorded on the result. A parameter that applies under no mode is reported as `not
applied` with the modes tried.

This is how the mode-to-setpoint mapping in spec 03 is established, rather than assumed.

A value that cannot be moved — a single-option field, or a bound with no room — is
skipped, not failed. Every other value is tried, including the ones that turn a device
off; a mode that is never written is a mode that is never confirmed.

A trial is skipped where the current value is outside its declared shape (spec 02). A
device in a state the shape does not describe is not a device to guess at.

### Restoring

After every trial on a device, a sweep reads the device once and re-writes any parameter
not holding the value it was found with, then confirms. It runs whether the trials
completed or were interrupted.

A parameter still holding a written value after the sweep is `not restored` and is listed
under its own heading, naming the device, the parameter and both values.

`--yes` skips the confirmation prompt, which states that the run changes every setting
on every device and puts them back. Exit status is non-zero if any trial failed.

### Summary

Printed at the end of a run:

- pass or fail per device, with the count of parameters that passed
- every failure, with its reason and the validation message where there was one
- any device left changed, listed separately and named as needing attention
- new and missing fields across the account, with the severities above

### One unit per configuration

A write run takes minutes per device, and exercising two identical units establishes
nothing the first did not. By default `exercise` covers one device per distinct
configuration and names the units each one stands for.

A configuration is the model, the firmware version, and the set of sections the device
reports. Model and firmware alone are not enough: two AC-V1-0 on one account run the same
firmware and differ in whether they carry `acConfig` and `modes.horizontalSwingState`, so
one would stand for the other and the difference would go untested.

Where several units share a configuration the representative is the lowest device id, so
repeated runs cover the same unit and its samples accumulate against one baseline.

`--all` exercises every device. `--device` targets one and overrides both.

## observe

`exercise` establishes which values a device accepts. It cannot establish what a value
means: a mode reported as 4 is a number until someone selects Heat in the app and the
number moves.

`observe` is that loop. It reads everything the account exposes for a device — the state
document, the device record, `/homes` and `/schedules` — waits for the operator to change
one thing in the Mysa app, reads again, and reports what moved.

Every readable surface, not just the state document: an app setting can have no state
field at all. Toggling early-on on a BB-V1-0 moves nothing in `/state/batch`; it moves
`schedGlobalOffset` on the device record. The snapshot covers the state document, the
device record, `/homes`, each home individually, `/schedules` and `/users`. An endpoint
that errors is recorded and does not stop the session.

`observe` sees state, not requests. A setting stored behind an endpoint this project does
not read cannot be found this way however many times it is toggled.

```

Change one setting in the Mysa app, then press Enter.  [q] finish

  modes.mode                     4 -> 0       (off)
  targetHeat.setpoint            20 -> 5

What did you change?  > turned the thermostat off
```

Measurements that drift on their own are dropped, and so is any field whose name ends in
`timestamp`, at any depth: those advance on their own and would bury the setting that
changed.

The label is recorded with the diff. A change touching several fields is recorded whole,
because that is itself the fact: turning a device off moved both its mode and its
setpoint.

Nothing is written to the device. The operator drives it.

### Unmapped values

`pymysa.meanings` holds the value-to-name maps that are established. A value a device
reports that is not in the map for its field is unmapped, and both `inspect` and
`observe` list them at the end of a run:

```
  Unmapped values (2):
    BB-V1-0    modes.mode = 4
    BB-V1-0    bbConfig.controlType = 7
```

That list is the agenda for an `observe` session. A field with no map at all is not
listed: an unmapped value is only meaningful where some values are mapped.

### Declared with no state field

A device can declare a setting writable that appears in no section of its state document
— `smart.smartAlerts.*` on both baseboard models. Such a setting cannot be exercised: a
write to it has nothing to read back, and guessing a section name is how a valid field
comes to look like a broken write path.

`inspect` lists them:

```
  Declared, no state field mapped (10):
    BB-V3-0    smart.smartAlerts.temperatureAlerts.high.enabled  (boolean)
    BB-V3-0    smart.smartAlerts.temperatureAlerts.high.threshold  (float)
```

Setting one in the app and running `observe` names where it lands, which is what adds it
to the capability-path map in spec 04 and to the catalogue. A setting can be declared per
device and stored per home — smart alerts are — so the snapshot covers `/homes` and
`/schedules` as well as the device's own surfaces.

## Samples

Raw captures are written verbatim:

```
docs/samples/raw/<model>/<read|write>/<device id>.json
```

Raw is local only. It carries device ids, serial numbers and device names, and
`docs/samples/raw/` is in `.gitignore`.

`process` redacts every raw capture into:

```
docs/samples/<model>/<read|write>/<device alias>.json
```

which is what a pull request adding a model carries. One redactor runs across the whole
tree, so a device holds the same alias in every file and samples remain cross-referenced
after redaction.

Grouping is by model because a sample is evidence about a model rather than about one
unit, and split by operation because a read describes a device and a write records what
it accepted.

## Redaction

Removed or replaced:

- account identifiers: owner, allowed users, home id, email, username
- device identifiers: device id, serial number, MAC, IP address
- location: postal code, address, city, province, country, latitude, longitude
- credentials and tokens
- `Name`, replaced with a positional label

Location patterns are anchored where a bare substring would catch a protocol field:
`city` matches `capacity`, and `state` matches `drState` and `SwingState`.

A pattern is checked against the captured samples before being added. A name that reads
as sensitive need not be: `geofence` sits in `cloudFeatures` beside `scheduling` and
`zoning` and holds a boolean.

Device ids are replaced consistently, in dictionary keys as well as values — `/state/batch`
is keyed by device id.

Redaction runs on a deny-list of key patterns and an allow-list of value shapes. A key
matching neither is retained and listed in `review` at the end of the file.
