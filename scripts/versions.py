"""The versions that have to agree.

The tag HACS installs a release at, the version Home Assistant reports from the
manifest, the SDK's own version, and the wheel the manifest requires are four spellings
of one number. CI runs this on every push so drift is found then, rather than by a
release failing.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "axelrtgs/mysa")


def wheel_url(version: str) -> str:
    return (
        f"pymysa@https://github.com/{REPOSITORY}/releases/download/"
        f"v{version}/pymysa-{version}-py3-none-any.whl"
    )


def disagreements(tag: str | None = None) -> list[str]:
    manifest = json.loads((ROOT / "custom_components/mysa/manifest.json").read_text())
    pyproject = tomllib.loads((ROOT / "packages/pymysa/pyproject.toml").read_bytes().decode())
    version = str(manifest["version"])
    sdk = str(pyproject["project"]["version"])
    requirement = str(manifest["requirements"][0])

    found = []
    if sdk != version:
        found.append(f"pymysa is {sdk}, the manifest says {version}")
    if requirement != wheel_url(version):
        found.append(f"the requirement is {requirement}, not {wheel_url(version)}")
    if tag is not None and tag.removeprefix("v") != version:
        found.append(f"the tag is {tag}, the manifest says {version}")
    return found


def main(argv: list[str]) -> int:
    found = disagreements(argv[0] if argv else None)
    for problem in found:
        print(problem, file=sys.stderr)
    if not found:
        manifest = json.loads((ROOT / "custom_components/mysa/manifest.json").read_text())
        print(f"versions agree at {manifest['version']}")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
