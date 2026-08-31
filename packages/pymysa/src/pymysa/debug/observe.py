"""Learning what a reported value means, by watching the operator change it.

`exercise` establishes which values a device accepts. Only a person selecting Heat in the
app establishes that the mode which then appears is heat.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from ..exceptions import MysaError
from ..meanings import name_of
from ..transport.rest import MysaRest
from .account import choose, collect
from .auth import prompt
from .samples import OBSERVE, write_raw

#: Measurements that move on their own. A change in one of these is the room, not the
#: operator, and reporting it would bury the setting that did change.
DRIFTING: frozenset[str] = frozenset({
    "coreTemperature", "current", "delta", "dutyCycle", "energy", "freeHeap",
    "humidity", "instantLoad", "lastConnected", "maxCurrent", "onTime",
    "powerConsumed", "rawTemperature", "roomTemperature", "rssi",
    "secondaryRawTemperature", "timestampEstimated", "vaDirection", "vaDrift",
    "vaIsSteadyState", "vaRateOfChange", "vaRateOfRateOfChange", "vaSteadyStateTemp",
    "voltage", "wattage",
})


@dataclass(frozen=True)
class Change:
    section: str
    field: str
    before: Any
    after: Any
    model: str | None = None

    def describe(self) -> str:
        if isinstance(self.before, tuple) or isinstance(self.after, tuple):
            return f"{self.section}.{self.field:<24} {self._membership()}"
        known = name_of(self.section, self.field, self.after, self.model)
        suffix = f"  ({known})" if known else ""
        return f"{self.section}.{self.field:<24} {self.before!r} -> {self.after!r}{suffix}"

    def _membership(self) -> str:
        """What entered and left a set, rather than both sets in full."""
        before = set(self.before or ())
        after = set(self.after or ())
        parts = []
        if after - before:
            parts.append("added " + ", ".join(repr(v) for v in sorted(after - before, key=repr)))
        if before - after:
            parts.append("removed " + ", ".join(repr(v) for v in sorted(before - after, key=repr)))
        return "; ".join(parts) or "reordered"


@dataclass
class Observation:
    label: str
    changes: list[Change] = field(default_factory=list)


#: Everything readable, so a setting stored outside the state document still shows up.
#: An app setting with no state field is otherwise invisible: toggling early-on on a
#: BB-V1-0 moves nothing in `/state/batch`.
async def snapshot(rest: MysaRest, device_id: str) -> dict[tuple[str, str], Any]:
    """Every value the account exposes for one device, keyed by source and path."""
    batch = await rest.get_state_batch([device_id])
    values = flatten(_document(batch, device_id))

    homes: dict[str, Any] = {}
    for source, call in (
        ("devices", rest.get_devices),
        ("homes", rest.get_homes),
        ("schedules", rest.get_schedules),
        ("users", rest.get_users),
    ):
        try:
            payload = await call()
        except MysaError as err:
            values[(source, "error")] = str(err)
            continue
        if source == "homes":
            homes = payload
        for path, value in _walk(payload):
            values[(source, path)] = value

    # `/homes` may summarise where the per-home record does not.
    for home_id in _home_ids(homes):
        try:
            payload = await rest.get_home(home_id)
        except MysaError as err:
            values[("home", f"{home_id}.error")] = str(err)
            continue
        for path, value in _walk(payload):
            values[("home", path)] = value
    return values


def _home_ids(homes: dict[str, Any]) -> list[str]:
    entries = homes.get("Homes") if isinstance(homes, dict) else None
    if not isinstance(entries, list):
        return []
    return [
        str(entry[key])
        for entry in entries
        if isinstance(entry, dict)
        for key in ("Id", "id", "HomeId")
        if key in entry
    ]


#: Keys that identify a list entry, most specific first. `/schedules` returns its array
#: in a different order on each read, so an index makes every entry look changed.
IDENTITY_KEYS = ("Id", "id", "Uuid", "uuid", "Device", "device", "Name", "name")


def _walk(node: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Arbitrary JSON as dotted paths. These surfaces have no fixed shape."""
    if isinstance(node, dict):
        found: list[tuple[str, Any]] = []
        for key, value in node.items():
            found += _walk(value, f"{prefix}.{key}" if prefix else str(key))
        return found
    if isinstance(node, list):
        if node and all(isinstance(item, (str, int, float, bool)) for item in node):
            # A list of scalars is a set: `SupportedCaps.modifiedKeys` is the enabled
            # modes, and the app rewrites its order whenever one is toggled. Comparing
            # by position turns one change into ten.
            return [(prefix, tuple(sorted(node, key=repr)))]
        found = []
        for label, value in _labelled(node):
            found += _walk(value, f"{prefix}[{label}]")
        return found
    return [(prefix, node)]


def _labelled(items: list[Any]) -> list[tuple[str, Any]]:
    """Label list entries by identity where they have one, otherwise by position."""
    key = _identity_key(items)
    if key is None:
        return [(str(index), value) for index, value in enumerate(items)]
    return [(f"{key}={item[key]}", item) for item in items]


def _identity_key(items: list[Any]) -> str | None:
    if not items or not all(isinstance(item, dict) for item in items):
        return None
    for key in IDENTITY_KEYS:
        values = [item.get(key) for item in items]
        if all(isinstance(v, (str, int)) for v in values) and len(set(values)) == len(values):
            return key
    return None


def flatten(document: dict[str, Any]) -> dict[tuple[str, str], Any]:
    """Every value in force, keyed by section and field."""
    flat: dict[tuple[str, str], Any] = {}
    for section, body in document.items():
        if not isinstance(body, dict):
            continue
        half = body.get("reported")
        source = half if isinstance(half, dict) else body
        for key, value in source.items():
            if key == "timestamp":
                continue
            if key == "reading" and isinstance(value, dict):
                for name, item in value.items():
                    if name == "timestamp":
                        continue
                    flat[(f"{section}.reading", name)] = item
            else:
                flat[(section, key)] = value
    return flat


def differences(
    before: dict[tuple[str, str], Any],
    after: dict[tuple[str, str], Any],
    model: str | None = None,
) -> list[Change]:
    """What moved between two reads, ignoring measurements that drift on their own."""
    changes: list[Change] = []
    for key in sorted(set(before) | set(after)):
        was, now = before.get(key), after.get(key)
        if was == now:
            continue
        changes.append(Change(key[0], key[1], was, now, model))
    return changes


async def session(
    rest: MysaRest,
    device_id: str,
    prompt: Callable[[str], Awaitable[str]],
    announce: Callable[[str], None] = print,
    ignore: frozenset[str] = DRIFTING,
    model: str | None = None,
) -> list[Observation]:
    """Prompt, re-read, report, label. Repeats until the operator finishes."""
    observations: list[Observation] = []
    before = await snapshot(rest, device_id)

    while True:
        answer = await prompt(
            "\nChange one setting in the Mysa app, then press Enter.  [q] finish  > "
        )
        if answer.strip().lower() == "q":
            return observations

        after = await snapshot(rest, device_id)
        changes = [c for c in differences(before, after, model) if _wanted(c, ignore)]
        before = after

        if not changes:
            announce("  nothing changed; give the cloud a moment and try again")
            continue
        for change in changes:
            announce(f"  {change.describe()}")

        label = await prompt("What did you change?  > ")
        observations.append(Observation(label.strip(), changes))


#: Name endings that mark a value the cloud moves on its own.
CLOCK_SUFFIXES = ("timestamp", "lastupdated", "lastconnected", "updatedat", "time")


def _wanted(change: Change, ignore: frozenset[str]) -> bool:
    """Drop what moves on its own: measurements, and clocks at any depth."""
    leaf = change.field.rsplit(".", 1)[-1]
    return leaf not in ignore and not leaf.lower().endswith(CLOCK_SUFFIXES)


def _document(batch: dict[str, Any], device_id: str) -> dict[str, Any]:
    entry = batch.get(device_id)
    data = entry.get("data") if isinstance(entry, dict) else None
    return data if isinstance(data, dict) else {}


async def run_observe(args: Any) -> int:
    async with aiohttp.ClientSession() as http:
        rest, devices, ids = await collect(args, http)
        device_id = ids[0] if len(ids) == 1 else await choose(devices, ids)
        record = devices[device_id]
        model = record.get("Model", "?")

        print(f"\nWatching {record.get('Name', '?')} [{model}].")
        print("Change one thing at a time so each value can be attributed.")
        observations = await session(rest, device_id, prompt, model=model)

        if not observations:
            print("\n  nothing recorded")
            return 0

        print(f"\n  {len(observations)} observation(s):")
        for item in observations:
            print(f"\n  {item.label}")
            for change in item.changes:
                print(f"    {change.describe()}")

        if not args.no_samples:
            payload = {
                "device": record,
                "observations": [
                    {
                        "label": o.label,
                        "changes": [
                            {
                                "section": c.section,
                                "field": c.field,
                                "before": c.before,
                                "after": c.after,
                            }
                            for c in o.changes
                        ],
                    }
                    for o in observations
                ],
            }
            print(f"\n  -> {write_raw(args.raw, model, OBSERVE, device_id, payload)}")
        return 0
