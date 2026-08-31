"""Cloud write payloads.

Every write is `POST /state/{device_id}/update` with a source tag and one shadow
section. Sections match the names `/state/batch` returns, so a write targets the same
document a read produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Identifies the caller on the write. Observed on every app-originated update.
SOURCE_APP = 3


@dataclass(frozen=True)
class Write:
    """One field change, as a section and the keys to set inside it."""

    section: str
    fields: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        return {"source": SOURCE_APP, self.section: dict(self.fields)}
