# Architecture

## Layout

```
mysa/
├── docs/
│   ├── provenance.md
│   ├── specs/00..09              the source of truth; every protocol fact is tagged
│   └── samples/                  captured payloads; drive the tests
├── packages/
│   └── pymysa/
│       └── src/pymysa/
│           ├── const.py          Cognito ids, endpoints, client headers
│           ├── auth.py           SRP login, refresh over plain HTTP
│           ├── transport/rest.py the only transport (spec 01)
│           ├── account.py        MysaAccount: discovery, refresh, homes
│           ├── capabilities.py   Capability, the codeset and the capability document
│           ├── devices/
│           │   ├── base.py       MysaDevice: identity and the cache
│           │   ├── maps.py       semantic name -> section and key, per model
│           │   ├── readings.py   semantic properties
│           │   ├── declaration.py capabilities, options and setpoint bounds
│           │   └── writing.py    setters and confirmation
│           ├── meanings.py       what a reported value means
│           ├── shapes.py         declared value shapes
│           ├── schedules.py      hold state, and the one write
│           ├── firmware.py       update availability
│           └── debug/            the harness: inspect | exercise | observe | process
├── custom_components/mysa/       the integration; at the root because HACS looks there
│   ├── coordinator.py            one per account; the only clock
│   ├── entity.py                 identity, availability, the write path
│   ├── climate.py  sensor.py  binary_sensor.py
│   ├── select.py   number.py  switch.py  button.py
│   └── config_flow.py
├── tests/                        the integration's tests
├── hacs.json  pyproject.toml
└── .github/workflows/ci.yml
```

The integration is not under `packages/` with the SDK. HACS walks the repository tree
for a top-level `custom_components/<domain>` and reads no path from `hacs.json`, so a
nested one is never found.

## Where model-specific behaviour lives

In `devices/maps.py`, `meanings.py` and the capability sources - nowhere else. A model is
a field map and, where its values are names, an entry in the meanings table. Transport,
account, telemetry and the whole integration are model-agnostic: nothing outside those
tables reads the model string to decide what a device supports.

There is one `MysaDevice` class rather than a subclass per model. A device is what its
field map and its declaration say it is, and a model absent from the map is built anyway:
it reports what it reports and every semantic name reads `None` until the model is
described.

## Where the integration gets its answers

The integration contains no protocol code (spec 00). It reads `device.capabilities` to
decide what exists, `device.options(...)` to decide what a control offers, semantic
properties to read, and `set_*` to write. Where it needs something the SDK does not
expose, the SDK gains it - `setpoint_range` and `firmware_update` were added that way -
rather than the integration learning a field name.

## Testing

- Protocol and entity tests both run against the payloads in `docs/samples/`, so what is
  asserted is what a device actually sends.
- Transport is faked at the boundary; no test makes a network call.
- `mypy --strict` on both packages, `ruff` on both, and hassfest on the integration.

## Tooling

`ruff` for lint. `mypy --strict`. `pytest` for both packages. Modules stay under 300
lines.
