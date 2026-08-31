"""Update availability. See docs/specs/09-sdk-surface.md."""

from __future__ import annotations

import pytest

from pymysa.account import MysaAccount
from pymysa.exceptions import TransportError
from pymysa.firmware import FirmwareUpdate

ANSWER = {"update": False, "installedVersion": "3.17.5.9", "allowedVersion": "3.17.5.9"}
FAILURE = {"error": "returned 500: Unable to determine allowed version"}


def test_an_answer_is_parsed():
    assert FirmwareUpdate.parse(ANSWER) == FirmwareUpdate(False, "3.17.5.9", "3.17.5.9")


def test_an_update_is_the_two_versions_differing_as_the_backend_reports_it():
    payload = {"update": True, "installedVersion": "5.1.9", "allowedVersion": "5.2.0"}

    assert FirmwareUpdate.parse(payload) == FirmwareUpdate(True, "5.1.9", "5.2.0")


@pytest.mark.parametrize("payload", [FAILURE, {}, None, {"update": "yes"}])
def test_anything_but_an_answer_is_no_answer(payload):
    """An endpoint that cannot answer has not said there is no update."""
    assert FirmwareUpdate.parse(payload) is None


DEVICES = {"DevicesObj": {"9070": {"Id": "9070", "Model": "BB-V3-0"},
                          "a4e5": {"Id": "a4e5", "Model": "AC-V1-0"}}}


class FakeRest:
    def __init__(self, answers):
        self.answers = answers
        self.reads: list[str] = []

    async def get_devices(self):
        return DEVICES

    async def get_capabilities(self, device_id):
        return {"features": {}}

    async def get_schedules(self):
        return {}

    async def get_homes(self):
        return {}

    async def get_state_batch(self, ids):
        return {}

    async def get_update_available(self, device_id):
        self.reads.append(device_id)
        answer = self.answers[device_id]
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeAuth:
    async def aclose(self):
        return None


async def _account(answers):
    account = MysaAccount(FakeAuth(), None)
    account.rest = FakeRest(answers)
    await account.discover()
    return account


async def test_every_discovered_device_is_read_once():
    account = await _account({"9070": ANSWER, "a4e5": ANSWER})

    await account.refresh_firmware()

    assert account.rest.reads == ["9070", "a4e5"]
    assert account.devices["9070"].firmware_update == FirmwareUpdate(
        False, "3.17.5.9", "3.17.5.9"
    )


async def test_a_device_the_endpoint_cannot_answer_for_does_not_stop_the_rest():
    """A BB-V3-0 returns 500 for its own device and is a working device (spec 09)."""
    account = await _account({"9070": TransportError("returned 500"), "a4e5": ANSWER})

    await account.refresh_firmware()

    assert account.devices["9070"].firmware_update is None
    assert account.devices["a4e5"].firmware_update is not None


async def test_an_unreadable_answer_leaves_the_last_one_standing():
    account = await _account({"9070": ANSWER, "a4e5": ANSWER})
    await account.refresh_firmware()

    account.rest.answers["9070"] = FAILURE
    await account.refresh_firmware()

    assert account.devices["9070"].firmware_update == FirmwareUpdate(
        False, "3.17.5.9", "3.17.5.9"
    )
