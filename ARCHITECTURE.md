# Architecture

## Layout

```
mysa/
├── docs/
│   ├── provenance.md
│   ├── specs/00..07
│   └── samples/                   captured payloads; drive the tests
├── packages/
│   ├── pymysa/
│   │   └── src/pymysa/
│   │       ├── const.py           Cognito ids, mode/fan/swing enums, key ids
│   │       ├── auth.py            Cognito session and refresh
│   │       ├── transport/
│   │       │   ├── rest.py
│   │       │   └── mqtt.py
│   │       ├── envelope.py        envelope build and parse
│   │       ├── capabilities.py    Capability enum, AC discovery
│   │       ├── fields.py          FieldMap, unwrapping, extraction
│   │       ├── devices/
│   │       │   ├── base.py        MysaDevice
│   │       │   ├── baseboard_v1.py
│   │       │   ├── baseboard_v2.py
│   │       │   ├── baseboard_v3.py
│   │       │   ├── ac_v1.py
│   │       │   ├── infloor_v1.py
│   │       │   ├── central_v1.py
│   │       │   └── registry.py
│   │       ├── telemetry.py
│   │       ├── client.py          MysaClient facade
│   │       └── debug/
│   │           ├── __main__.py    capture | replay | redact
│   │           ├── session.py
│   │           ├── redact.py
│   │           └── scripts/       declarative step sequences
│   └── homeassistant-mysa/
│       └── custom_components/mysa/
│           ├── coordinator.py
│           ├── entity.py
│           ├── climate.py  sensor.py  binary_sensor.py
│           ├── select.py   number.py  switch.py  update.py
│           └── config_flow.py
└── .github/workflows/
```

## Device classes

A device class declares everything model-specific: matching, command type, field map,
which fields are wrapped, capabilities, and whether it is verified. Transport, protocol,
telemetry and integration code are model-agnostic.

Adding a model is one file in `devices/` and one registry entry.

```python
class BaseboardV1(MysaDevice):
    MODEL_MATCH = ModelMatch(prefix="BB-V1")
    COMMAND_TYPE = 1
    VERIFIED = True
    WRAPPED_FIELDS = frozenset({"CorrectedTemp", "SensorTemp", "Humidity"})
    FIELDS = FieldMap(
        current_temperature="CorrectedTemp",
        target_temperature="SetPoint",
        humidity="Humidity",
        current="Current",
        voltage="Voltage",
        duty_cycle="Duty",
    )
    CAPABILITIES = frozenset({
        Capability.TARGET_TEMPERATURE, Capability.MODE, Capability.CURRENT,
        Capability.VOLTAGE, Capability.DUTY_CYCLE, Capability.LOCK,
        Capability.BRIGHTNESS, Capability.PROXIMITY, Capability.ECO_MODE,
    })
```

## Testing

- Protocol tests run against the payloads in `docs/samples/`.
- Each device class has a test asserting every semantic field resolves against its
  sample, and that a value absent from the payload resolves to `None`.
- Debug harness bundles are replayed as regression tests.
- Transport is mocked at the boundary; unit tests make no network calls.

## Tooling

`ruff` for lint and format. `mypy --strict` on `pymysa`. `pytest` for both packages.
