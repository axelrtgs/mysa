"""Debug harness.

    python -m pymysa.debug inspect  [--device <id>]
    python -m pymysa.debug exercise [--device <id>] [--yes]
    python -m pymysa.debug process

`inspect` reads every endpoint the account exposes and reports what each device carries.
`exercise` writes every parameter a device supports, confirms it, and puts it back.
Both write raw captures under docs/samples/raw/, which stays local; `process` redacts
them into docs/samples/ for sharing.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import aiohttp

from ..capabilities import undeclared
from ..devices import semantics
from ..exceptions import MysaError
from .account import collect
from .auth import prompt
from .baseline import (
    Difference,
    check_values,
    compare,
    compare_peers,
    failed,
    load,
    peers,
)
from .coverage import representatives
from .exercise import DeviceReport, exercise_device
from .observe import run_observe
from .redact import Redactor
from .report import (
    as_dict,
    report_differences,
    report_undeclared,
    report_unmapped,
    summarise,
)
from .samples import (
    RAW_ROOT,
    READ,
    SAMPLES_ROOT,
    WRITE,
    process,
    slug,
    write_raw,
)
from .survey import DeviceSurvey, survey


def main() -> int:
    parser = argparse.ArgumentParser(prog="pymysa.debug")
    parser.add_argument("-v", "--verbose", action="store_true", help="log HTTP activity")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("inspect", "dump everything the account exposes, per device"),
        ("exercise", "write every supported parameter, confirm it, and restore it"),
        ("observe", "watch what changes while you drive the Mysa app"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--device", help="device id; omit for every device")
        cmd.add_argument(
            "--raw",
            type=Path,
            default=RAW_ROOT,
            help=f"directory for raw captures (default: {RAW_ROOT}/)",
        )
        cmd.add_argument(
            "--samples",
            type=Path,
            default=SAMPLES_ROOT,
            help=f"committed samples to compare against (default: {SAMPLES_ROOT}/)",
        )
        cmd.add_argument(
            "--no-samples", action="store_true", help="report only; write nothing"
        )
        cmd.add_argument("--session", type=Path)
        cmd.add_argument("--login", action="store_true")
        if name == "exercise":
            cmd.add_argument("--yes", action="store_true", help="skip the confirmation")
            cmd.add_argument(
                "--all",
                action="store_true",
                dest="every",
                help="exercise every device, not one per configuration",
            )
            cmd.add_argument("--settle", type=float, default=1.0)
            cmd.add_argument("--timeout", type=float, default=20.0)

    pro = sub.add_parser(
        "process", help="redact raw captures into the publishable samples tree"
    )
    pro.add_argument("--raw", type=Path, default=RAW_ROOT)
    pro.add_argument("--out", type=Path, default=SAMPLES_ROOT)

    args = parser.parse_args()
    _configure_logging(verbose=args.verbose)

    if args.command == "process":
        return _process(args)
    try:
        runner = {"inspect": _inspect, "exercise": _exercise, "observe": run_observe}[
            args.command
        ]
        return asyncio.run(runner(args))
    except KeyboardInterrupt:
        print("\naborted", file=sys.stderr)
        return 130
    except MysaError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


#: botocore and urllib3 log full request bodies at DEBUG, which includes the Cognito id
#: token. Never raise these above WARNING.
NOISY_LOGGERS = ("botocore", "boto3", "urllib3", "botocore.hooks", "aiohttp.client")


def _configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)-7s %(name)s: %(message)s"
    )
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    if verbose:
        logging.getLogger("pymysa").setLevel(logging.DEBUG)


def _process(args: argparse.Namespace) -> int:
    if not args.raw.exists():
        print(f"no raw captures in {args.raw}", file=sys.stderr)
        return 1
    results = process(args.raw, args.out)
    for item in results:
        print(f"  {item.source}  ->  {item.destination}")
        if item.review:
            print(f"     review before sharing: {', '.join(item.review[:6])}")
    print(f"\n  {len(results)} sample(s) written to {args.out}")
    return 0


async def _inspect(args: argparse.Namespace) -> int:
    async with aiohttp.ClientSession() as http:
        rest, devices, ids = await collect(args, http)
        batch = await rest.get_state_batch(ids)
        account = {
            "homes": await _endpoint(rest.get_homes),
            "schedules": await _endpoint(rest.get_schedules),
        }
        for name, payload in account.items():
            state = "error" if "error" in payload else f"{len(payload)} key(s)"
            print(f"  /{name}: {state}")
        surveys: list[DeviceSurvey] = []
        unmapped_settings: dict[str, list[tuple[str, str]]] = {}

        for device_id in ids:
            record = devices[device_id]
            document = (batch.get(device_id) or {}).get("data", {})
            item = survey(device_id, record, document)
            surveys.append(item)

            print(f"\n  {item.describe()}")
            for section in sorted(item.sections):
                print(f"    {section:<26} {', '.join(item.sections[section])}")

            if args.no_samples:
                continue
            capabilities = await _endpoint(rest.get_capabilities, device_id)
            unmapped_settings[slug(item.model)] = undeclared(capabilities)
            sample: dict[str, Any] = {
                "device": record,
                "state": batch.get(device_id),
                "capabilities": capabilities,
                "update_available": await _endpoint(rest.get_update_available, device_id),
                "sections": item.sections,
                "account": account,
            }
            print(f"    -> {write_raw(args.raw, item.model, READ, device_id, sample)}")

        documents = {i: (batch.get(i) or {}).get("data", {}) for i in ids}
        differences = _differences(surveys, documents, args.samples)
        report_differences(differences)
        report_unmapped({slug(s.model): documents[s.device_id] for s in surveys})
        report_undeclared(unmapped_settings)
        return 1 if failed(differences) else 0


async def _endpoint(call: Any, *args: Any) -> dict[str, Any]:
    """An endpoint that errors is recorded with its error rather than omitted."""
    try:
        payload: dict[str, Any] = await call(*args)
    except MysaError as err:
        return {"error": str(err)}
    return payload


async def _exercise(args: argparse.Namespace) -> int:
    async with aiohttp.ClientSession() as http:
        rest, devices, ids = await collect(args, http)

        batch = await rest.get_state_batch(ids)
        documents = {i: (batch.get(i) or {}).get("data", {}) for i in ids}
        if args.device or args.every:
            stands_for: dict[str, list[str]] = {i: [] for i in ids}
        else:
            stands_for = representatives({i: devices[i] for i in ids}, documents)
            ids = sorted(stands_for)
            for chosen, others in sorted(stands_for.items()):
                if others:
                    names = ", ".join(devices[o].get("Name", o) for o in others)
                    print(f"  {devices[chosen].get('Name', chosen)} stands for {names}")

        print(
            f"\nThis writes every value of every supported parameter on {len(ids)} "
            "device(s),\nincluding turning them off and on, and restores the original "
            "values at the end.\n"
        )
        if not args.yes and (
            await prompt("Continue? [y/N] > ")
        ).lower() not in ("y", "yes"):
            print("not run")
            return 0

        reports: list[DeviceReport] = []
        for device_id in ids:
            record = devices[device_id]
            report = await exercise_device(
                rest,
                device_id,
                record.get("Name", "?"),
                record.get("Model", "?"),
                args.settle,
                args.timeout,
                capabilities=await _endpoint(rest.get_capabilities, device_id),
            )
            reports.append(report)
            if not args.no_samples:
                path = write_raw(
                    args.raw, report.model, WRITE, device_id, as_dict(report)
                )
                print(f"  -> {path}")

        after = await rest.get_state_batch(ids)
        documents = {i: (after.get(i) or {}).get("data", {}) for i in ids}
        surveys = [survey(i, devices[i], documents[i]) for i in ids]
        differences = _differences(surveys, documents, args.samples)
        return 1 if summarise(reports, differences) else 0


def _differences(
    surveys: list[DeviceSurvey],
    documents: dict[str, dict[str, Any]],
    samples: Path,
) -> list[Difference]:
    """Field differences against the committed sample, and values outside their shape."""
    found: list[Difference] = []
    for item in surveys:
        model = slug(item.model)
        # Per model: how much a missing field matters is what that model's device class
        # reads it as, and the maps differ (spec 02).
        names = semantics(item.model)
        alias = Redactor().device_alias(item.device_id)
        against_own = compare(model, item.sections, load(samples, model, alias), names)
        found += against_own
        found += compare_peers(
            model,
            item.sections,
            peers(samples, model, alias),
            frozenset((d.section, d.field) for d in against_own),
        )
        found += check_values(model, documents.get(item.device_id, {}), names)
    return found


if __name__ == "__main__":
    raise SystemExit(main())
