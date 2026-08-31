"""Verbose mode must never raise botocore above WARNING.

botocore logs full request bodies at DEBUG, which contain the Cognito id token and the
STS session credentials.
"""

from __future__ import annotations

import logging

from pymysa.debug.__main__ import NOISY_LOGGERS, _configure_logging


def test_verbose_enables_only_pymysa() -> None:
    _configure_logging(verbose=True)
    assert logging.getLogger("pymysa").level == logging.DEBUG
    for name in NOISY_LOGGERS:
        level = logging.getLogger(name).level
        assert level >= logging.WARNING, f"{name} would leak credentials at {level}"


def test_quiet_mode_leaves_everything_at_warning() -> None:
    _configure_logging(verbose=False)
    for name in NOISY_LOGGERS:
        assert logging.getLogger(name).level >= logging.WARNING


def test_botocore_is_covered() -> None:
    assert "botocore" in NOISY_LOGGERS
    assert "urllib3" in NOISY_LOGGERS
