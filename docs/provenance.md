# Provenance

This project is written from the specifications in `docs/specs/`. It documents protocol
facts — field names, message shapes, enum values, key ids, endpoint paths — and
implements against them. No source from another project is copied, translated or used as
a structural template.

Protocol facts are tagged in the specs by source:

| tag | meaning |
|---|---|
| `[observed]` | captured from hardware, sample in `docs/samples/` |
| `[mit-sdk]` | documented in `bourquep/mysa-js-sdk` (MIT), attributed in `NOTICE.md` |
| `[inferred]` | deduced from behaviour, not yet confirmed against a device |
