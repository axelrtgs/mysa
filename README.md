# mysa

Python SDK and Home Assistant integration for Mysa smart thermostats.

| path | contents |
|---|---|
| `packages/pymysa` | Python SDK. No Home Assistant dependency. |
| `custom_components/mysa` | Home Assistant custom integration. Depends on `pymysa`. |

The integration sits at the repository root because that is where HACS looks: it walks
the tree for a top-level `custom_components/<domain>` and reads no path from `hacs.json`.

See `docs/specs/` for the specifications everything is written from.

## Installing in Home Assistant

Through HACS as a custom repository, or by copying `custom_components/mysa` into your
Home Assistant `config/custom_components/`.

HACS downloads files from `raw.githubusercontent.com` and release assets from
`github.com/.../releases/download/...`, with no authorization header on either, so it
can only install from a repository that is public. Its own GitHub login covers the API
calls it makes to read a repository, not the downloads.

Tagging a release puts that version in the HACS version picker, which offers the five
most recent. The tag and `manifest.json`'s `version` have to agree - CI refuses to
publish a release where they do not - because HACS installs the repository at the tag
while Home Assistant reports what the manifest says. Either way `pymysa` has to be installable:
Home Assistant runs `uv pip install pymysa==0.1.0` from the manifest when the entry is
set up, so the package needs to be on an index the instance can reach.

Then add **Mysa** from *Settings -> Devices & services*. Setup asks for the email and
password you use in the app. The password is used once, for the SRP login; what is
stored is a refresh token, and the password itself only if you ask for it to be kept.
Where the account holds more than one home, a second step asks which to set up - devices
in a home you do not choose are neither created nor polled.

You get one thermostat per device, with the modes, fan speeds and swing positions that
device declares, plus its measurements, its interface settings, and a button to release
a schedule hold. Everything is gated on what the device declares: a control with fewer
than two options is not a control, and a field being present is not a feature.

The polling interval and the home selection are in the integration's options. One
request covers the whole account however many devices it holds.

### Known gaps

Documented in the specs, and not bugs to rediscover:

- An AC-V1-0 serves no capability document, so its controls come from the codeset and
  from observed value sets (spec 04).
- Horizontal swing is gated on a codeset declaration neither sample unit serves, so it
  is not offered even on the unit that reports the field (spec 04).
- Schedule definitions are not exposed: every capture's day lists are empty (spec 08).
- The sensor-mode control is not exposed: `tracking.tracking` holds numbers and its
  declared names are tied to none of them (spec 09).
- `energy` is declared in kilowatt hours on evidence that does not exist yet, and
  `powerConsumed` is left unitless. Spec 05 records what settles both.

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

## Development

```
pytest                            # both packages, from the repository root
ruff check custom_components tests
mypy --strict custom_components
```

`packages/pymysa` carries its own configuration and is checked the same way. Entity
tests run against the redacted captures in `docs/samples`, so what is asserted is what a
device actually sends.

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
