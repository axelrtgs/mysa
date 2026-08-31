# Captured payloads

Redacted captures from real hardware. Account identifiers (owner, users, home id, device
id, serial, IP) are replaced. Protocol tests assert field maps against these files.

```
docs/samples/<model>/<read|write>/<device alias>.json
```

`read` is what a device reports: its state document, capabilities and the sections it
carries. `write` is what it accepted: every parameter exercised, with the result and any
validation message.

Grouped by model because a sample is evidence about a model rather than about one unit.
A device holds the same alias across every file, so samples stay cross-referenced after
redaction.

| file | model | firmware |
|---|---|---|
| `bb-v1-state.json` | BB-V1-0 | 3.17.3.1 |
| `bb-v3-state.json` | BB-V3-0 | 5.1.9 |
| `ac-v1-caps-beta.json` | AC-V1-0 (pre-release unit) | 3.17.5.9 |
| `ac-v1-caps-retail.json` | AC-V1-0 (retail unit) | 3.17.5.9 |

Those four predate the layout above and are kept until a run replaces them.

## Contributing a capture

```
pymysa-debug inspect
pymysa-debug exercise
pymysa-debug process
```

`inspect` and `exercise` write raw, unredacted captures to `docs/samples/raw/`, which is
gitignored. `process` redacts them into the tree above. Submit what `process` produced.
