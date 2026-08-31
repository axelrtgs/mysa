# homeassistant-mysa

A Home Assistant custom integration for Mysa thermostats, on top of
[`pymysa`](../pymysa). It contains no protocol code and does not branch on model: what a
device can do comes from the SDK's capability set, and what it reports comes from the
SDK's semantic properties.

See `docs/specs/06-ha-entities.md` for the entity spec this implements, and
`docs/specs/00-overview.md` for why the two halves are split this way.

## Install

Copy `custom_components/mysa` into your Home Assistant `config/custom_components/`,
install `pymysa`, and restart. Then add **Mysa** from *Settings -> Devices & services*.

Setup asks for the email and password you use in the app. The password is used once, for
the SRP login; what is stored is a refresh token, and the password itself only if you ask
for it to be kept. Where the account holds more than one home, a second step asks which
to set up - devices in a home you do not choose are neither created nor polled.

## What you get

One thermostat per device, with the modes, fan speeds and swing positions that device
declares, plus its measurements, its interface settings, and a button to release a
schedule hold. Everything is gated on what the device declares: a control with fewer than
two options is not a control, and a field being present is not a feature.

The polling interval and the home selection are in the integration's options. One request
covers the whole account however many devices it holds.

## Known gaps

These are documented in the specs and are not bugs to rediscover:

- An AC-V1-0 serves no capability document, so its controls come from the codeset and
  from observed value sets (spec 04).
- Horizontal swing is gated on a codeset declaration neither sample unit serves, so it is
  not offered even on the unit that reports the field (spec 04).
- Schedule definitions are not exposed: every capture's day lists are empty (spec 08).
- The sensor-mode control is not exposed: `tracking.tracking` holds numbers and its
  declared names are tied to none of them (spec 09).
- `energy` is declared in kilowatt hours on evidence that does not exist yet, and
  `powerConsumed` is left unitless. Spec 05 records what settles both.

## Development

```
pytest                  # from packages/homeassistant-mysa
ruff check custom_components tests
mypy --strict custom_components
python -m script.hassfest --integration-path <path to custom_components/mysa>
```

Tests run against the redacted captures in `docs/samples`, so an entity is asserted
against what a device actually sends.
