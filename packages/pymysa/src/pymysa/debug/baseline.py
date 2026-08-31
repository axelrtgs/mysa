"""Comparing a capture against the committed sample for its model.

The samples in `docs/samples/<model>/read/` are the record of what a model reports. A
field present there and absent from a capture is a regression; a field present in a
capture and absent there is new. A model with no committed sample has no baseline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..fields import Criticality, criticality
from ..shapes import shape_of

ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"

_SEVERITY = {
    Criticality.CRITICAL: ERROR,
    Criticality.IMPORTANT: WARNING,
    Criticality.INFORMATIONAL: INFO,
}


@dataclass(frozen=True)
class Difference:
    model: str
    section: str
    field: str
    kind: str            # "new" | "missing" | "unexpected"
    semantic: str | None
    severity: str

    detail: str = ""

    def describe(self) -> str:
        where = f"{self.section}.{self.field}"
        if self.kind == "unexpected":
            return f"{self.severity:<8} {self.model:<10} {where} {self.detail}"
        role = self.semantic or "not read"
        return f"{self.severity:<8} {self.model:<10} {where} {self.kind} ({role})"


def load(samples_root: Path, model: str, alias: str) -> dict[str, frozenset[str]]:
    """Fields per section, from this unit's own committed read sample.

    Per unit, not per model: two units of one model differ, and a baseline unioned
    across a model reports one unit's fields as missing from another.
    """
    path = samples_root / model / "read" / f"{alias}.json"
    if not path.is_file():
        return {}
    sections = json.loads(path.read_text()).get("sections", {})
    return {
        section: frozenset(fields)
        for section, fields in sections.items()
        if isinstance(fields, list)
    }


def peers(samples_root: Path, model: str, alias: str) -> dict[str, frozenset[str]]:
    """Fields the other committed units of this model report."""
    directory = samples_root / model / "read"
    if not directory.is_dir():
        return {}
    found: dict[str, set[str]] = {}
    for path in sorted(directory.glob("*.json")):
        if path.stem == alias:
            continue
        for section, fields in json.loads(path.read_text()).get("sections", {}).items():
            if isinstance(fields, list):
                found.setdefault(section, set()).update(fields)
    return {section: frozenset(fields) for section, fields in found.items()}


def compare_peers(
    model: str,
    observed: dict[str, list[str]],
    other: dict[str, frozenset[str]],
    exclude: frozenset[tuple[str, str]] = frozenset(),
) -> list[Difference]:
    """Fields some units of this model carry and others do not. Never an error.

    Reported from one side only. A unit having a field its peer lacks, and the peer
    lacking it, are one fact; printing both reads as two findings.

    `exclude` drops fields already reported against the unit's own baseline, which would
    otherwise appear a third time.
    """
    if not other:
        return []
    differences: list[Difference] = []
    for section in sorted(set(observed) | set(other)):
        seen = frozenset(observed.get(section, ()))
        known = other.get(section, frozenset())
        for field in sorted(seen - known):
            if (section, field) in exclude:
                continue
            differences.append(
                Difference(model, section, field, "varies between units", None, INFO)
            )
    return differences


def check_values(
    model: str,
    document: dict[str, Any],
    semantics: dict[tuple[str, str], str],
) -> list[Difference]:
    """Values falling outside their declared shape.

    Only shaped fields are checked; an unshaped field produces no report whatever it
    holds.
    """
    found: list[Difference] = []
    for section, body in _bodies(document):
        for field, value in sorted(body.items()):
            shape = shape_of(section, field)
            if shape is None or shape.holds(value, body):
                continue
            semantic = semantics.get((section, field))
            found.append(
                Difference(
                    model, section, field, "unexpected", semantic,
                    _SEVERITY[criticality(semantic)],
                    f"= {value!r} (expected {shape.describe(body)})",
                )
            )
    return found


def _bodies(document: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Section name and the values in force, including nested telemetry readings."""
    bodies: list[tuple[str, dict[str, Any]]] = []
    for section, body in document.items():
        if not isinstance(body, dict):
            continue
        half = body.get("reported")
        bodies.append((section, half if isinstance(half, dict) else body))
        reading = body.get("reading")
        if isinstance(reading, dict):
            bodies.append((f"{section}.reading", reading))
    return bodies


def compare(
    model: str,
    observed: dict[str, list[str]],
    baseline: dict[str, frozenset[str]],
    semantics: dict[tuple[str, str], str],
) -> list[Difference]:
    """Differences between a capture and its baseline.

    `semantics` maps (section, field) to the semantic name a device class reads it as.
    A pair absent from it is not read, and its loss is informational.
    """
    if not baseline:
        return []

    differences: list[Difference] = []
    for section in sorted(set(observed) | set(baseline)):
        seen = frozenset(observed.get(section, ()))
        known = baseline.get(section, frozenset())
        for field in sorted(seen - known):
            differences.append(
                Difference(model, section, field, "new", None, INFO)
            )
        for field in sorted(known - seen):
            semantic = semantics.get((section, field))
            differences.append(
                Difference(
                    model, section, field, "missing", semantic,
                    _SEVERITY[criticality(semantic)],
                )
            )
    return differences


def failed(differences: list[Difference]) -> bool:
    return any(d.severity == ERROR for d in differences)
