"""Trial outcomes. See docs/specs/07-debug-harness.md.

A refusal is a fact about the device, not a defect. Only a device left changed, or a
request that cannot be classified, fails a run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..refusals import ERROR

PASSED = "passed"
NOT_APPLIED = "not applied"
NOT_RESTORED = "not restored"

#: Outcomes that mean the run found a problem, rather than found a fact.
FAILING = frozenset({NOT_RESTORED, ERROR})


@dataclass(frozen=True)
class Result:
    parameter: str
    original: Any
    written: Any
    status: str
    detail: str = ""
    #: Modes under which the value did apply, for a mode-scoped parameter.
    applied_in: tuple[Any, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == PASSED

    @property
    def failing(self) -> bool:
        return self.status in FAILING

    def describe(self) -> str:
        line = f"{self.parameter:<38} {self.status:<13} {self.original!r} -> {self.written!r}"
        if self.applied_in:
            line += f"  applies in mode {', '.join(str(m) for m in self.applied_in)}"
        return f"{line}  {self.detail}" if self.detail else line
