"""Where captured samples land.

Two stages. The harness writes raw, unredacted captures:

    docs/samples/raw/<model>/<read|write>/<device id>.json

Raw stays local - it carries device ids, serials and names, and is gitignored. `process`
then redacts and rewrites them as:

    docs/samples/<model>/<read|write>/<device alias>.json

which is what a pull request adding support for a new device carries. Grouping is by
model because a sample is evidence about a model rather than about one unit, and split
by operation because a read describes a device and a write records what it accepted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .redact import Redactor

READ = "read"
WRITE = "write"
OBSERVE = "observe"

SAMPLES_ROOT = Path("docs/samples")
RAW_ROOT = SAMPLES_ROOT / "raw"


def write_raw(
    root: Path, model: str, operation: str, device_id: str, payload: dict[str, Any]
) -> Path:
    """Write a capture verbatim. Never redacted; never committed."""
    directory = root / slug(model) / operation
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{device_id}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


@dataclass(frozen=True)
class Processed:
    source: Path
    destination: Path
    review: list[str]


def process(raw_root: Path, out_root: Path) -> list[Processed]:
    """Redact every raw capture into the publishable tree.

    One redactor for the whole run, so a device keeps the same alias across every file
    and samples can still be cross-referenced after redaction.
    """
    redactor = Redactor()
    results: list[Processed] = []
    for source in sorted(raw_root.rglob("*.json")):
        relative = source.relative_to(raw_root)
        if len(relative.parts) != 3:
            continue
        model, operation, _ = relative.parts
        payload = json.loads(source.read_text())

        before = len(redactor.review)
        scrubbed = redactor.scrub(payload)
        review = redactor.review[before:]
        scrubbed["review"] = review

        destination = out_root / model / operation / f"{redactor.device_alias(source.stem)}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(scrubbed, indent=2) + "\n")
        results.append(Processed(source, destination, review))
    return results


def slug(model: str) -> str:
    """Model names are already path-safe; anything unexpected is made so."""
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in model) or "unknown"
