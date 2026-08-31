# Captured payloads

Redacted payloads from real hardware. Account identifiers (owner, users, home id,
device id, serial, IP, key material) are replaced. Protocol tests assert field maps
against these files.

| file | model | firmware |
|---|---|---|
| `bb-v1-state.json` | BB-V1-0 | 3.17.3.1 |
| `bb-v3-state.json` | BB-V3-0 | 5.1.9 |
| `ac-v1-caps-beta.json` | AC-V1-0 (pre-release unit) | 3.17.5.9 |
| `ac-v1-caps-retail.json` | AC-V1-0 (retail unit) | 3.17.5.9 |

## Contributing a capture

Run the debug harness (spec 07) against hardware and submit the output. Captures for
unverified models are what move them to verified.
