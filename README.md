# mysa

Python SDK and Home Assistant integration for Mysa smart thermostats.

| package | contents |
|---|---|
| `packages/pymysa` | Python SDK. No Home Assistant dependency. |
| `packages/homeassistant-mysa` | Home Assistant custom integration. |

Status: specification. See `docs/specs/`.

## Hardware support

| model | status |
|---|---|
| BB-V1 | verified |
| BB-V3 | verified for reads; write command type not yet captured |
| AC-V1 | verified |
| BB-V2 | untested |
| BB-V2 Lite | untested; reports no current, so no power or energy entities |
| INF-V1 | untested |
| ST-V1 | untested |

Untested models are implemented from documented protocol facts. An unrecognised field
resolves to unavailable rather than to a wrong value.

**If you own an untested model**, run the debug harness and send the capture; that is
what moves a model to verified.

```
python -m pymysa.debug capture --script full
```

The harness redacts account and device identifiers before writing. See
[`docs/specs/07-debug-harness.md`](docs/specs/07-debug-harness.md).

## Design

- Power and energy come from measured current and voltage. Nothing is estimated.
- Values the device does not report are unavailable, never defaulted.
- Model-specific behaviour lives in device classes; nothing else branches on model.

## Provenance

Written from the specifications in `docs/specs/`, which document protocol facts. No
source from another project is copied. See [`docs/provenance.md`](docs/provenance.md)
and `NOTICE.md`.

Not affiliated with Mysa. Uses undocumented APIs that may change without notice.
