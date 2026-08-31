# 07 — Debug harness

A guided capture tool shipped with `pymysa`. It records protocol traffic while the
operator performs a scripted sequence of actions in the Mysa app, and writes a redacted
bundle suitable for adding to `docs/samples/` or attaching to an issue.

Purposes: confirming write encodings for commands marked `[inferred]`, adding support
for untested models, and re-capturing after a Mysa-side protocol change.

## Invocation

```
python -m pymysa.debug capture [--device <id>] [--script <name>] [--out <path>]
python -m pymysa.debug replay <bundle>          # re-parse a bundle against current maps
python -m pymysa.debug redact <bundle>          # re-run redaction
```

Credentials come from `MYSA_USERNAME` / `MYSA_PASSWORD` or an interactive prompt. They
are never written to the bundle.

## Capture session

1. Authenticate; list devices with model, firmware and verification status.
2. Operator selects a device.
3. Record the device record, `SupportedCaps` and initial state as the baseline.
4. Subscribe to the device's MQTT topics and begin recording every inbound and outbound
   message with a monotonic timestamp.
5. Run the step sequence for the selected script.
6. Write the bundle.

## Step sequence

Each step prints an instruction, waits, then records.

```
Step 4 of 17 — Vertical swing

  In the Mysa app, turn vertical swing ON for "Hallway".
  Press Enter when done, [s] if this control is unavailable on this unit,
  [r] to repeat the previous step, [q] to finish early.
```

On Enter the harness waits for the settle window (default 5 s), captures every message
received since the instruction, diffs the resulting state against the previous step, and
records:

```jsonc
{
  "step": "vertical_swing_on",
  "status": "captured",              // captured | unavailable | skipped
  "instruction": "Turn vertical swing ON",
  "messages": [ { "direction": "in", "topic": "...", "payload": { ... } } ],
  "state_diff": { "SwingState": { "before": 1, "after": 2 } }
}
```

`unavailable` is a result, not a failure. A control absent on the hardware is a fact
about that model and is recorded as such.

## Scripts

| script | steps |
|---|---|
| `baseline` | device record, caps, state. No operator action. |
| `climate` | setpoint up, setpoint down, mode through each supported value, power off, power on |
| `ac` | `climate` plus fan speed through each value, vertical swing on/off, horizontal swing through each position |
| `config` | lock on/off, auto brightness on/off, brightness min/max, proximity on/off, eco on/off, temperature format C/F, setpoint limits |
| `full` | all of the above |

Scripts are declarative and live in `pymysa/debug/scripts/`. A step names the semantic
command it exercises so `replay` can assert the captured encoding against the field map.

## Bundle format

```jsonc
{
  "version": 1,
  "captured_at": "2026-08-30T22:14:00Z",
  "pymysa_version": "0.1.0",
  "device": { "model": "AC-V1-0", "firmware": "3.17.5.9", "supported_caps": { ... } },
  "script": "ac",
  "steps": [ ... ]
}
```

## Redaction

Applied before writing. Removed or replaced:

- account identifiers: owner, allowed users, home id, email, username
- device identifiers: device id, serial number, MAC, IP address
- credentials and tokens: session tokens, AWS credentials, key hashes, `privKeyOk`,
  `pubKeyHash`
- `Name`, replaced with a positional label

Device ids are replaced consistently within a bundle so message correlation survives.

Redaction runs on a deny-list of key patterns and an allow-list of value shapes. A key
matching neither is retained and flagged in a `review` list at the end of the bundle for
the operator to check before sharing.

## Replay

`replay` parses a bundle against the current device classes and reports, per step,
whether the semantic fields resolved and whether the observed write encoding matches
what `encode` produces. This turns a capture into a regression test: bundles committed
to `docs/samples/` are exercised by the test suite.
