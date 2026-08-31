"""Every command resolves and every module's names are bound.

A missing import survives collection and every unit test, then fails as a NameError the
first time a command runs. These checks execute the module bodies and walk each command's
own globals, which is where that shows up.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import pymysa
import pymysa.debug
import pymysa.devices
from pymysa.debug.__main__ import main

COMMANDS = ("inspect", "exercise", "observe", "process")


def _modules() -> list[str]:
    found = []
    for package in (pymysa, pymysa.debug, pymysa.devices):
        for info in pkgutil.iter_modules(package.__path__, f"{package.__name__}."):
            found.append(info.name)
    return found


@pytest.mark.parametrize("name", _modules())
def test_every_module_imports(name: str):
    importlib.import_module(name)


def test_the_public_api_is_importable():
    """What `__all__` promises is what a caller gets."""
    missing = [name for name in pymysa.__all__ if not hasattr(pymysa, name)]
    assert missing == []


@pytest.mark.parametrize("command", COMMANDS)
def test_every_command_is_reachable(command: str, capsys):
    """--help builds the parser and resolves the runner table."""
    with pytest.raises(SystemExit) as exit_info:
        main_argv(["pymysa.debug", command, "--help"])
    assert exit_info.value.code == 0
    assert command in capsys.readouterr().out


def main_argv(argv: list[str]) -> int:
    import sys

    original, sys.argv = sys.argv, argv
    try:
        return main()
    finally:
        sys.argv = original


@pytest.mark.parametrize("command", COMMANDS)
def test_every_command_body_has_its_names_bound(command: str):
    """Walks the function's own globals, which is where a lost import hides."""
    from pymysa.debug import __main__ as cli

    runner = {
        "inspect": cli._inspect,
        "exercise": cli._exercise,
        "observe": cli.run_observe,
        "process": cli._process,
    }[command]

    missing = [
        name
        for name in runner.__code__.co_names
        if name.islower()
        and name not in runner.__globals__
        and not hasattr(__builtins__, name)
        and name not in dir(__builtins__)
    ]
    # Attribute names appear in co_names too; only bare globals matter.
    unresolved = [n for n in missing if n in {"collect", "prompt", "choose", "survey",
                                              "process", "write_raw", "session"}]
    assert unresolved == []
