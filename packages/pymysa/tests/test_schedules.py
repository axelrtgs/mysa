"""Schedule records and hold state."""

from __future__ import annotations

from datetime import UTC

from pymysa.schedules import ScheduleHold, parse_schedules

PAYLOAD = {"Schedules": [
    {"Device": "807d", "ScheduledActions": {"Monday": [], "Tuesday": []}},
    {"Device": "3c71", "ScheduledActions": {"Monday": []}},
]}


class FakeRest:
    def __init__(self):
        self.writes: list[tuple[str, dict]] = []

    async def update_state(self, device_id, payload):
        section = next(k for k in payload if k != "source")
        self.writes.append((section, dict(payload[section])))
        return {"message": "ok"}


def test_entries_are_identified_by_device_not_position():
    """The array comes back in a different order on each read (spec 08)."""
    schedules = parse_schedules(PAYLOAD)

    assert [s.device_id for s in schedules] == ["807d", "3c71"]
    assert schedules[0].days == ("Monday", "Tuesday")


def test_an_empty_schedule_is_recognisable_as_empty():
    """Every capture has empty day lists; a caller should be able to tell."""
    assert parse_schedules(PAYLOAD)[0].empty


def test_a_payload_with_no_schedules_parses_to_nothing():
    assert parse_schedules({}) == ()


def test_the_hold_reads_its_three_fields():
    hold = ScheduleHold("9070", {"holding": True, "resolved": True,
                                 "nextEvent": 1788170400}, FakeRest())

    assert hold.holding is True
    assert hold.resolved is True
    assert hold.next_event is not None
    assert hold.next_event.tzinfo is UTC


def test_a_hold_with_no_end_reports_none():
    """`holding` true with no nextEvent is holding until changed (spec 08)."""
    hold = ScheduleHold("9070", {"holding": True}, FakeRest())

    assert hold.next_event is None


async def test_releasing_writes_the_flag_off():
    rest = FakeRest()
    hold = ScheduleHold("9070", {"holding": True}, rest)

    await hold.release()

    assert rest.writes == [("schedule", {"holding": False})]
    assert hold.holding is False
