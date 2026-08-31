<img src="https://brands.home-assistant.io/mysa/icon.png" width="96" align="right" alt="">

# Mysa for Home Assistant

Control Mysa baseboard thermostats and mini-split controllers from Home Assistant, over
Mysa's own cloud API. No account settings are changed, nothing is written to a device
that the device has not declared it can do, and no value is estimated.

[![hacs](https://img.shields.io/badge/HACS-custom%20repository-41bdf5)](https://hacs.xyz)
![home assistant](https://img.shields.io/badge/Home%20Assistant-2026.2%2B-41bdf5)
![license](https://img.shields.io/badge/license-MIT-blue)

## What you get

One thermostat per device, plus the readings and settings that device actually has:

- **Climate** — modes, setpoint, and on an AC unit the fan speeds and swing positions its
  codeset can express.
- **Sensors** — temperature, humidity, and on a baseboard the current, voltage, power,
  duty cycle and energy. Signal strength, electricity rate and when the device last
  reported are diagnostics.
- **Settings** — keypad lock, display unit and brightness, setpoint limits, heater type,
  early-on, wake on approach, adaptive brightness, temperature offset, Climate+.
- **Schedules** — whether a hold is in force, when it next changes, and a button to
  release it.

Everything is gated on what the device declares. A control with fewer than two options is
not a control, and a field being present is not a feature: a BB-V1-0 takes an
adaptive-brightness write and has no light sensor to act on it, so it gets no switch.

One request covers the whole account, however many devices it holds.

## Install

Add `https://github.com/axelrtgs/mysa` to HACS as a custom repository, category
**Integration**, then install and restart. Or copy `custom_components/mysa` into your
`config/custom_components/`.

Then add **Mysa** from *Settings → Devices & services*. It asks for the email and
password you use in the app. The password is used once, for the SRP login; what is kept
is a refresh token, and the password itself only if you ask for it to be. Where the
account holds more than one home, a second step asks which to set up — devices in a home
you do not choose are neither created nor polled.

The polling interval and the home selection are in the integration's options.

## Supported hardware

| model | status |
|---|---|
| Baseboard V1 (`BB-V1`) | verified |
| Baseboard V3 (`BB-V3`) | verified |
| AC / mini-split (`AC-V1`) | verified |
| Baseboard V2, V2 Lite | untested |
| In-floor (`INF-V1`), Central (`ST-V1`) | untested |

Untested models are built from the same field maps and declarations as the rest. An
unrecognised field resolves to unavailable rather than to a wrong value, so an untested
model is incomplete rather than misleading.

**If you own one**, `pymysa-debug inspect` reports what it sends and `process` redacts the
capture for a pull request. That is what moves a model to verified.

## Known limits

- An AC unit serves no capability document, so its controls come from its codeset and
  from observed value sets. Horizontal swing is not offered even where the field is
  reported: no codeset seen declares it.
- Schedule definitions are not exposed — every capture's day lists are empty, so their
  shape is unknown. Holds are.
- `energy` is declared in kilowatt hours on evidence that does not exist yet, and
  `powerConsumed` carries no unit at all.
- Not affiliated with Mysa. This uses undocumented APIs that may change without notice.

## Under the hood

Two packages: [`pymysa`](packages/pymysa), a Python SDK with no Home Assistant
dependency, and the integration, which contains no protocol code and never branches on
model — what a device can do comes from the SDK's capability set.

Every protocol fact is written down in [`docs/specs/`](docs/specs) and tagged `[observed]`
(captured from hardware) or `[inferred]` (deduced, not confirmed), against the redacted
captures in [`docs/samples/`](docs/samples) that the tests run on. The specification comes
first: if it does not cover something, or disagrees with a capture, it is fixed before the
code is.

```
pytest                              # both packages, from the repository root
ruff check custom_components tests
mypy --strict custom_components
```

Written from those specifications. No source from another project is copied — see
[`docs/provenance.md`](docs/provenance.md) and [`NOTICE.md`](NOTICE.md).
