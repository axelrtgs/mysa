# 00 — Overview

## Packages

| package | contents |
|---|---|
| `pymysa` | Python SDK. No Home Assistant imports. |
| `homeassistant-mysa` | Home Assistant custom integration. Depends on `pymysa`. Contains no protocol code. |

## Layers

| layer | responsibility |
|---|---|
| transport | HTTP calls, authentication, session renewal |
| state | parsing the state document into sections and fields |
| device | field mapping, capability declaration, write construction |
| integration | Home Assistant entities and coordination |

Model-specific behaviour exists only in device classes. No other layer branches on model.

## Transport

The cloud REST API is the only transport. It carries every field every model reports and
accepts every write, and its state document has the same shape for all models.

Devices also publish on an MQTT topic. That surface covers a subset of models, carries a
subset of the fields, and is not used.

## Data rules

- A field the device does not report resolves to `None`. Absent values are never
  defaulted, substituted or estimated.
- `0` and `None` are distinct. A device reporting 0 A is reporting a measurement.
- Power and energy are derived only from measured electrical values. Devices that do not
  report current expose no power or energy entities.
- Capability sets that resolve empty are not exposed. No control is presented without
  options.

## Requirements

- Python 3.12+
- Full type annotations; `mypy --strict` on `pymysa`
- No blocking I/O on the event loop
- Modules under 300 lines
