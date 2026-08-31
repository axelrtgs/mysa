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
| BB-V3 | verified |
| AC-V1 | verified |
| BB-V2 | untested |
| BB-V2 Lite | untested; reports no current, so no power or energy entities |
| INF-V1 | untested |
| ST-V1 | untested |

Untested models are implemented from documented protocol facts. An unrecognised field
resolves to unavailable rather than to a wrong value.

**If you own an untested model**, run the debug harness and send the samples; that is
what moves a model to verified.

```
pymysa-debug inspect     # what the device reports
pymysa-debug exercise    # what it accepts; writes each setting and puts it back
pymysa-debug process     # redact the captures for a pull request
```

Raw captures stay local. `process` redacts them into `docs/samples/`. See
[`docs/specs/07-debug-harness.md`](docs/specs/07-debug-harness.md).

## Design

- Devices are read and written through the cloud REST API. It covers every model and
  every field; the MQTT surface devices also publish on does not, and is not used.
- Power and energy come from measured current and voltage. Nothing is estimated.
- Values the device does not report are unavailable, never defaulted.
- Model-specific behaviour lives in device classes; nothing else branches on model.

## Provenance

Written from the specifications in `docs/specs/`, which document protocol facts. No
source from another project is copied. See [`docs/provenance.md`](docs/provenance.md)
and `NOTICE.md`.

Not affiliated with Mysa. Uses undocumented APIs that may change without notice.
