"""Discovery, refresh, and what a failing device does to either."""

from __future__ import annotations

from pymysa.account import MysaAccount, _records
from pymysa.exceptions import TransportError

DEVICES = {"DevicesObj": {
    "9070": {"Id": "9070", "Name": "Living Room", "Model": "BB-V3-0", "Home": "591d"},
    "a4e5": {"Id": "a4e5", "Name": "Hallway", "Model": "AC-V1-0", "Home": "cabin"},
}}

HOMES = {"Homes": [
    {"Id": "591d", "Name": "My Home", "ERate": "0.0616"},
    {"Id": "cabin", "Name": "The Cabin"},
]}

STATE = {
    "9070": {"data": {"identity": {"reported": {"model": "BB-V3-0"}},
                      "latestTelemetry": {"isConnected": True,
                                          "reading": {"roomTemperature": 23.7}}}},
    "a4e5": {"data": {"identity": {"reported": {"model": "AC-V1-0"}},
                      "latestTelemetry": {"isConnected": False,
                                          "reading": {"roomTemperature": 21.5}}}},
}


class FakeRest:
    def __init__(self, devices=None, capability_error=(), device_error=None):
        self.devices = devices if devices is not None else DEVICES
        self.capability_error = set(capability_error)
        self.device_error = device_error
        self.batches: list[list[str]] = []
        self.home_reads = 0

    async def get_devices(self):
        if self.device_error:
            raise self.device_error
        return self.devices

    async def get_capabilities(self, device_id):
        if device_id in self.capability_error:
            raise TransportError("capabilities not available for this app version")
        return {"features": {}}

    async def get_schedules(self):
        return {"Schedules": [{"Device": "9070", "ScheduledActions": {"Monday": []}}]}

    async def get_homes(self):
        self.home_reads += 1
        return HOMES

    async def get_state_batch(self, ids):
        self.batches.append(list(ids))
        return {i: STATE[i] for i in ids if i in STATE}


class FakeAuth:
    async def aclose(self):
        return None


def _account(rest, **kwargs):
    account = MysaAccount(FakeAuth(), session=None, **kwargs)
    account.rest = rest
    return account


async def test_discovery_builds_one_device_per_record():
    account = _account(FakeRest())

    await account.discover()

    assert sorted(account.devices) == ["9070", "a4e5"]
    assert account.devices["9070"].name == "Living Room"


async def test_a_device_serving_no_capability_document_is_still_discovered():
    """An AC-V1-0 returns 404 for it and is a working device (spec 04)."""
    account = _account(FakeRest(capability_error={"a4e5"}))

    await account.discover()

    assert "a4e5" in account.devices
    assert account.unavailable == {}


async def test_refresh_reads_every_device_in_one_batch():
    rest = FakeRest()
    account = _account(rest)
    await account.discover()

    await account.refresh()

    assert rest.batches == [["9070", "a4e5"]]
    assert account.devices["9070"].current_temperature == 23.7
    assert account.devices["a4e5"].available is False


async def test_refresh_without_discovery_reads_nothing():
    rest = FakeRest()
    account = _account(rest)

    await account.refresh()

    assert rest.batches == []


async def test_a_device_object_survives_rediscovery():
    """A caller may hold one; a new object on every poll would strand its subscribers."""
    account = _account(FakeRest())
    await account.discover()
    device = account.devices["9070"]

    await account.discover()

    assert account.devices["9070"] is device


async def test_a_device_that_leaves_the_account_is_dropped():
    rest = FakeRest()
    account = _account(rest)
    await account.discover()

    rest.devices = {"DevicesObj": {"9070": DEVICES["DevicesObj"]["9070"]}}
    await account.discover()

    assert sorted(account.devices) == ["9070"]


async def test_schedules_are_read_at_discovery():
    account = _account(FakeRest())

    await account.discover()

    assert [s.device_id for s in account.schedules] == ["9070"]


async def test_an_optional_read_that_fails_does_not_fail_discovery():
    """Devices are the point; homes and schedules are context."""
    rest = FakeRest()

    async def boom():
        raise TransportError("500")

    rest.get_schedules = boom
    account = _account(rest)

    await account.discover()

    assert sorted(account.devices) == ["9070", "a4e5"]
    assert account.schedules == ()


async def test_records_read_both_shapes():
    assert sorted(_records(DEVICES)) == ["9070", "a4e5"]
    assert sorted(_records({"Devices": [{"Id": "9070"}]})) == ["9070"]
    assert _records({}) == {}


async def test_the_electricity_rate_comes_from_the_home():
    """`ERate` on the home record, served as a string."""
    account = _account(FakeRest())
    await account.discover()

    home = account.home_of(account.devices["9070"])

    assert home is not None
    assert home.electricity_rate == 0.0616


async def test_a_rate_that_will_not_parse_is_not_a_rate():
    from pymysa.homes import Home

    assert Home.parse({"Id": "x", "ERate": "n/a"}).electricity_rate is None
    assert Home.parse({"Id": "x"}).electricity_rate is None


async def test_a_renamed_device_keeps_its_object():
    rest = FakeRest()
    account = _account(rest)
    await account.discover()
    device = account.devices["9070"]

    rest.devices = {"DevicesObj": {
        "9070": {"Id": "9070", "Name": "Lounge", "Model": "BB-V3-0"},
        "a4e5": DEVICES["DevicesObj"]["a4e5"],
    }}
    await account.discover()

    assert account.devices["9070"] is device
    assert device.name == "Lounge"


async def test_discovery_takes_every_home_by_default():
    account = _account(FakeRest())

    await account.discover()

    assert account.included_homes is None
    assert sorted(account.devices) == ["9070", "a4e5"]


async def test_discovery_can_be_limited_to_one_home():
    account = _account(FakeRest(), homes=["591d"])

    await account.discover()

    assert sorted(account.devices) == ["9070"]


async def test_an_excluded_device_is_never_polled():
    """The point of the limit: a device the user did not choose costs nothing."""
    rest = FakeRest()
    account = _account(rest, homes=["591d"])
    await account.discover()

    await account.refresh()

    assert rest.batches == [["9070"]]


async def test_narrowing_the_limit_drops_what_it_now_excludes():
    rest = FakeRest()
    account = _account(rest)
    await account.discover()
    assert sorted(account.devices) == ["9070", "a4e5"]

    account.limit_to(["cabin"])
    await account.discover()

    assert sorted(account.devices) == ["a4e5"]


async def test_widening_the_limit_brings_devices_back():
    account = _account(FakeRest(), homes=["591d"])
    await account.discover()

    account.limit_to(None)
    await account.discover()

    assert sorted(account.devices) == ["9070", "a4e5"]


async def test_a_device_belonging_to_no_home_is_not_in_a_chosen_one():
    rest = FakeRest({"DevicesObj": {"x": {"Id": "x", "Model": "BB-V1-0"}}})
    account = _account(rest, homes=["591d"])

    await account.discover()

    assert account.devices == {}


async def test_homes_can_be_listed_without_discovering_devices():
    """A setup flow needs the list before it commits to discovering anything."""
    rest = FakeRest()
    account = _account(rest)

    homes = await account.list_homes()

    assert sorted(homes) == ["591d", "cabin"]
    assert homes["591d"].name == "My Home"
    assert account.devices == {}
    assert rest.batches == []


async def test_an_unknown_home_id_is_named(caplog):
    account = _account(FakeRest())
    await account.list_homes()

    account.limit_to(["591d", "nowhere"])

    assert "nowhere" in caplog.text
