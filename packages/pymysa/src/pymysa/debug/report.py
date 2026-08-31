"""Printing a run."""

from __future__ import annotations

from typing import Any

from ..meanings import unmapped
from ..refusals import REJECTED, UNSUPPORTED_KIND
from .baseline import Difference, failed
from .exercise import DeviceReport
from .results import NOT_APPLIED


def as_dict(report: DeviceReport) -> dict[str, Any]:
    return {
        "device": report.device_id,
        "model": report.model,
        "passed": report.passed,
        "results": [
            {
                "parameter": r.parameter,
                "original": r.original,
                "written": r.written,
                "status": r.status,
                "detail": r.detail,
                "applied_in": list(r.applied_in),
            }
            for r in report.results
        ],
    }


def summarise(reports: list[DeviceReport], differences: list[Difference]) -> bool:
    print("\n" + "=" * 72)
    for report in reports:
        verdict = "PASS" if report.passed else "FAIL"
        print(
            f"  {verdict}  {report.name:<24} {report.model:<10} "
            f"{report.confirmed}/{len(report.results)} confirmed"
        )

    # A refusal is a fact about the device. Report it without calling it a failure.
    for status, heading in (
        (UNSUPPORTED_KIND, "Not supported by the device"),
        (REJECTED, "Refused by the schema"),
        (NOT_APPLIED, "Accepted, not applied"),
    ):
        found = [(r, x) for r in reports for x in r.results if x.status == status]
        if found:
            print(f"\n  {heading} ({len(found)}):")
            for report, result in found:
                print(f"    {report.name}: {result.describe()}")

    failures = [(r, x) for r in reports for x in r.results if x.failing]
    if failures:
        print("\n  Failures:")
        for report, result in failures:
            print(f"    {report.name}: {result.describe()}")

    scoped = [(r, x) for r in reports for x in r.results if x.applied_in]
    if scoped:
        print("\n  Mode-scoped parameters:")
        for report, result in scoped:
            modes = ", ".join(str(m) for m in result.applied_in)
            print(f"    {report.name}: {result.parameter} applies in mode {modes}")

    unrestored = [(r, x) for r in reports for x in r.unrestored]
    if unrestored:
        print("\n  LEFT CHANGED - these devices need attention:")
        for report, result in unrestored:
            print(f"    {report.name}: {result.parameter} is {result.written!r}, "
                  f"was {result.original!r}")

    report_differences(differences)
    return bool(failures) or failed(differences)


def report_differences(differences: list[Difference]) -> None:
    if not differences:
        print("\n  No field or value differences against the committed samples.")
        return
    for kind, heading in (
        ("missing", "Missing fields"),
        ("unexpected", "Unexpected values"),
        ("new", "New fields"),
        ("varies between units", "Carried by some units of this model and not others"),
    ):
        found = [d for d in differences if d.kind == kind]
        if not found:
            continue
        # One difference found on several units is one difference.
        counted: dict[str, int] = {}
        for item in found:
            counted[item.describe()] = counted.get(item.describe(), 0) + 1
        print(f"\n  {heading} ({len(counted)}):")
        for line, count in counted.items():
            suffix = f"  [{count} units]" if count > 1 else ""
            print(f"    {line}{suffix}")


def report_unmapped(models: dict[str, dict[str, Any]]) -> None:
    """Values with no established name. This list is the agenda for `observe`."""
    found: set[tuple[str, str, str, Any]] = set()
    for model, document in models.items():
        for section, body in document.items():
            if not isinstance(body, dict):
                continue
            half = body.get("reported")
            source = half if isinstance(half, dict) else body
            for field_name, value in unmapped(section, source, model):
                found.add((model, section, field_name, value))

    if not found:
        print("\n  No unmapped values.")
        return
    print(f"\n  Unmapped values ({len(found)}):")
    for model, section, field_name, value in sorted(found, key=lambda f: (f[0], f[1], f[2])):
        print(f"    {model:<10} {section}.{field_name} = {value!r}")


def report_undeclared(found: dict[str, list[tuple[str, str]]]) -> None:
    """Settings a device declares writable that no state field is mapped to."""
    rows = {
        (model, path, kind)
        for model, paths in found.items()
        for path, kind in paths
    }
    if not rows:
        return
    print(f"\n  Declared, no state field mapped ({len(rows)}):")
    for model, path, kind in sorted(rows):
        print(f"    {model:<10} {path}  ({kind})")
