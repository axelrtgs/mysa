"""Exception hierarchy. See docs/specs/09-sdk-surface.md.

The names are the spec's, and two of them do not end in Error: `UnsupportedCommand` and
`ValueRefused` read as what the backend did, which is what a caller catches them for.
"""
# ruff: noqa: N818

from __future__ import annotations


class MysaError(Exception):
    """Base for every error raised by pymysa."""


class AuthenticationError(MysaError):
    """Credentials rejected, or a session could not be refreshed."""


class TransportError(MysaError):
    """REST transport failure."""


class UnsupportedCommand(MysaError):
    """The device does not declare the capability for this command."""


class ValueRefused(MysaError):
    """The backend refused the value against its schema.

    A fact about the request, not about the device: the constraint it names is the
    device's own, and the same write with a permitted value is accepted.
    """
