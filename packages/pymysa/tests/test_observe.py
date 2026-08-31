"""Watching what changes while the operator drives the app."""

from __future__ import annotations

from pymysa.debug.observe import DRIFTING, differences, flatten, session, snapshot

DOCUMENT = {
    "modes": {"reported": {"mode": 4, "timestamp": 10}},
    "targetHeat": {"reported": {"setpoint": 20, "timestamp": 10}},
    "latestTelemetry": {"isConnected": True, "reading": {"roomTemperature": 21.5}},
    "drState": {"state": "none"},
}


def test_flatten_reaches_shadow_sections_and_nested_readings():
    flat = flatten(DOCUMENT)
    assert flat[("modes", "mode")] == 4
    assert flat[("latestTelemetry.reading", "roomTemperature")] == 21.5
    assert flat[("drState", "state")] == "none"


def test_timestamps_are_not_values():
    """A write bumps sibling timestamps, so they would drown out the real change."""
    assert ("modes", "timestamp") not in flatten(DOCUMENT)


def test_differences_report_both_sides():
    before = flatten(DOCUMENT)
    after = dict(before)
    after[("modes", "mode")] = 0

    (change,) = differences(before, after)
    assert (change.section, change.field, change.before, change.after) == (
        "modes", "mode", 4, 0,
    )


def test_a_known_value_is_named_in_the_description():
    before = flatten(DOCUMENT)
    after = dict(before)
    after[("modes", "mode")] = 0

    assert "(off)" in differences(before, after)[0].describe()


def test_measurements_that_drift_are_not_operator_changes():
    assert "roomTemperature" in DRIFTING
    assert "humidity" in DRIFTING
    assert "mode" not in DRIFTING


class FakeRest:
    def __init__(self, states, homes=None, schedules=None) -> None:
        self.states = list(states)
        self.homes = list(homes) if homes else None
        self.schedules = list(schedules) if schedules else None

    def _next(self, queue):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    async def get_state_batch(self, ids):
        return {ids[0]: {"data": self._next(self.states)}}

    async def get_devices(self):
        return {"DevicesObj": {}}

    async def get_homes(self):
        return self._next(self.homes) if self.homes else {}

    async def get_schedules(self):
        return self._next(self.schedules) if self.schedules else {}

    async def get_users(self):
        return {}

    async def get_home(self, home_id):
        return {}


def _answers(*replies):
    queue = list(replies)

    async def prompt(_message: str) -> str:
        return queue.pop(0)

    return prompt


async def test_a_session_records_the_change_and_its_label():
    changed = {"modes": {"reported": {"mode": 0}}}
    rest = FakeRest([{"modes": {"reported": {"mode": 4}}}, changed, changed])

    observations = await session(
        rest, "aaa", _answers("", "turned it off", "q"), lambda _: None
    )

    assert len(observations) == 1
    assert observations[0].label == "turned it off"
    assert observations[0].changes[0].after == 0


async def test_a_drifting_measurement_alone_is_not_a_change():
    warm = {"latestTelemetry": {"reading": {"roomTemperature": 22.0}}}
    rest = FakeRest([{"latestTelemetry": {"reading": {"roomTemperature": 21.5}}}, warm, warm])
    said: list[str] = []

    observations = await session(rest, "aaa", _answers("", "q"), said.append)

    assert observations == []
    assert any("nothing changed" in line for line in said)


async def test_finishing_immediately_records_nothing():
    rest = FakeRest([DOCUMENT])
    assert await session(rest, "aaa", _answers("q"), lambda _: None) == []


def test_the_telemetry_timestamp_is_not_a_change():
    """It advances on its own every reporting interval and buries the real change."""
    flat = flatten({"latestTelemetry": {"reading": {"timestamp": 1788160214,
                                                    "roomTemperature": 21.5}}})
    assert ("latestTelemetry.reading", "timestamp") not in flat
    assert ("latestTelemetry.reading", "roomTemperature") in flat


def test_a_section_appearing_for_the_first_time_is_a_change():
    """A device with no schedule has no schedule section until one is configured."""
    before = flatten({"modes": {"reported": {"mode": 0}}})
    after = flatten({"modes": {"reported": {"mode": 0}},
                     "schedule": {"holding": True, "nextEvent": 1788170400}})

    fields = {(c.section, c.field, c.before, c.after) for c in differences(before, after)}
    assert ("schedule", "holding", None, True) in fields
    assert ("schedule", "nextEvent", None, 1788170400) in fields


def test_a_structured_value_is_described_without_crashing():
    """cloudFeatures.cloudEarlyOn is an object, not a scalar."""
    before = flatten({"cloudFeatures": {"cloudEarlyOn": {"enabled": False}}})
    after = flatten({"cloudFeatures": {"cloudEarlyOn": {"enabled": True}}})

    (change,) = differences(before, after)
    assert "enabled" in change.describe()


async def test_a_setting_stored_outside_the_state_document_is_still_seen():
    """Toggling early-on on a BB-V1 moves nothing in /state/batch."""
    state = {"modes": {"reported": {"mode": 0}}}
    rest = FakeRest(
        [state],
        homes=[{"Homes": [{"Id": "h1", "earlyOn": False}]},
               {"Homes": [{"Id": "h1", "earlyOn": True}]},
               {"Homes": [{"Id": "h1", "earlyOn": True}]}],
    )

    observations = await session(rest, "aaa", _answers("", "early on", "q"), lambda _: None)

    (observation,) = observations
    assert observation.changes[0].section == "homes"
    assert observation.changes[0].field == "Homes[Id=h1].earlyOn"
    assert observation.changes[0].after is True


async def test_an_endpoint_that_errors_does_not_stop_the_session():
    class Broken(FakeRest):
        async def get_schedules(self):
            from pymysa.exceptions import TransportError

            raise TransportError("/schedules returned 404")

    rest = Broken([{"modes": {"reported": {"mode": 0}}}])
    assert await session(rest, "aaa", _answers("q"), lambda _: None) == []


async def test_a_timestamp_at_any_depth_is_not_a_change():
    """Nested surfaces carry their own timestamps that advance on their own."""
    state = {"modes": {"reported": {"mode": 0}}}
    rest = FakeRest(
        [state],
        schedules=[{"Schedules": [{"updatedTimestamp": 1}]},
                   {"Schedules": [{"updatedTimestamp": 2}]},
                   {"Schedules": [{"updatedTimestamp": 2}]}],
    )
    said: list[str] = []

    assert await session(rest, "aaa", _answers("", "q"), said.append) == []
    assert any("nothing changed" in line for line in said)


SCHEDULES_A = {"Schedules": [{"Device": "aaa", "Name": "Weekday"},
                             {"Device": "bbb", "Name": "Weekend"}]}
SCHEDULES_B = {"Schedules": [{"Device": "bbb", "Name": "Weekend"},
                             {"Device": "aaa", "Name": "Weekday"}]}


async def test_a_reordered_list_is_not_a_change():
    """/schedules returns its array in a different order on each read."""
    rest = FakeRest([{"modes": {"reported": {"mode": 0}}}],
                    schedules=[SCHEDULES_A, SCHEDULES_B, SCHEDULES_B])
    said: list[str] = []

    assert await session(rest, "aaa", _answers("", "q"), said.append) == []
    assert any("nothing changed" in line for line in said)


async def test_a_real_change_inside_a_reordered_list_is_still_seen():
    moved = {"Schedules": [{"Device": "bbb", "Name": "Weekend"},
                           {"Device": "aaa", "Name": "Holiday"}]}
    rest = FakeRest([{"modes": {"reported": {"mode": 0}}}],
                    schedules=[SCHEDULES_A, moved, moved])

    (observation,) = await session(
        rest, "aaa", _answers("", "renamed it", "q"), lambda _: None
    )
    (change,) = observation.changes
    assert change.field == "Schedules[Device=aaa].Name"
    assert (change.before, change.after) == ("Weekday", "Holiday")


async def test_a_list_of_objects_without_identities_falls_back_to_position():
    from pymysa.debug.observe import _walk

    entries = {"rows": [{"a": 1}, {"a": 2}]}
    assert dict(_walk(entries)) == {"rows[0].a": 1, "rows[1].a": 2}


async def test_a_last_updated_clock_is_not_a_change():
    """Mode.LastUpdated moves whenever the cloud touches the record."""
    rest = FakeRest([{"modes": {"reported": {"mode": 0}}}],
                    homes=[{"Homes": [{"Id": "h1", "LastUpdated": 1}]},
                           {"Homes": [{"Id": "h1", "LastUpdated": 2}]},
                           {"Homes": [{"Id": "h1", "LastUpdated": 2}]}])

    assert await session(rest, "aaa", _answers("", "q"), lambda _: None) == []


CAPS_ALL = {"SupportedCaps": {"modifiedKeys": [1, 2, 3, 7, 4, 6, 5, 11, 10, 9, 8, 47]}}
CAPS_NO_HEAT = {"SupportedCaps": {"modifiedKeys": [1, 2, 4, 6, 5, 11, 10, 9, 8, 47]}}


def test_a_list_of_scalars_is_compared_as_a_set():
    """modifiedKeys is rewritten in a fresh order whenever a mode is toggled."""
    from pymysa.debug.observe import _walk

    shuffled = {"SupportedCaps": {"modifiedKeys": [47, 8, 9, 10, 11, 5, 6, 4, 7, 3, 2, 1]}}
    assert dict(_walk(CAPS_ALL)) == dict(_walk(shuffled))


def test_a_set_change_reports_what_entered_and_left():
    from pymysa.debug.observe import _walk

    before, after = dict(_walk(CAPS_ALL)), dict(_walk(CAPS_NO_HEAT))
    (change,) = differences(before, after)

    assert "removed 3, 7" in change.describe()
    assert "added" not in change.describe()


def test_a_restored_mode_reports_what_was_added():
    from pymysa.debug.observe import _walk

    before, after = dict(_walk(CAPS_NO_HEAT)), dict(_walk(CAPS_ALL))
    (change,) = differences(before, after)

    assert "added 3, 7" in change.describe()


async def test_toggling_available_modes_is_one_observation_not_ten():
    rest = FakeRest([{"modes": {"reported": {"mode": 3}}}])
    rest.devices_payload = [{"DevicesObj": {"aaa": CAPS_ALL}},
                            {"DevicesObj": {"aaa": CAPS_NO_HEAT}},
                            {"DevicesObj": {"aaa": CAPS_NO_HEAT}}]

    async def get_devices():
        return rest._next(rest.devices_payload)

    rest.get_devices = get_devices
    (observation,) = await session(
        rest, "aaa", _answers("", "heat off", "q"), lambda _: None
    )
    assert len(observation.changes) == 1


async def test_each_home_is_read_individually_as_well_as_listed():
    """`/homes` may summarise where the per-home record does not."""
    seen: list[str] = []

    class WithHomes(FakeRest):
        async def get_homes(self):
            return {"Homes": [{"Id": "h1"}, {"Id": "h2"}]}

        async def get_home(self, home_id):
            seen.append(home_id)
            return {"Id": home_id, "alerts": {"high": False}}

    rest = WithHomes([{"modes": {"reported": {"mode": 0}}}])
    await snapshot(rest, "aaa")

    assert seen == ["h1", "h2"]


async def test_a_home_endpoint_that_errors_is_recorded_not_fatal():
    class Broken(FakeRest):
        async def get_homes(self):
            return {"Homes": [{"Id": "h1"}]}

        async def get_home(self, home_id):
            from pymysa.exceptions import TransportError

            raise TransportError("/homes/h1 returned 404")

    values = await snapshot(Broken([{"modes": {"reported": {"mode": 0}}}]), "aaa")
    assert ("home", "h1.error") in values


async def test_a_home_level_setting_is_seen():
    payloads = [{"Id": "h1", "alerts": {"high": False}},
                {"Id": "h1", "alerts": {"high": True}},
                {"Id": "h1", "alerts": {"high": True}}]

    class WithAlerts(FakeRest):
        async def get_homes(self):
            return {"Homes": [{"Id": "h1"}]}

        async def get_home(self, home_id):
            return self._next(payloads)

    rest = WithAlerts([{"modes": {"reported": {"mode": 0}}}])
    (observation,) = await session(
        rest, "aaa", _answers("", "temperature alert on", "q"), lambda _: None
    )
    (change,) = observation.changes
    assert (change.section, change.field) == ("home", "alerts.high")
