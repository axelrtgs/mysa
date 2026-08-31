"""Declared value shapes."""

from __future__ import annotations

from pymysa.shapes import SHAPES, Shape, shape_of


def test_an_enum_accepts_only_its_values():
    shape = shape_of("physicalInterface", "format")
    assert shape.holds("C")
    assert shape.holds("F")
    assert not shape.holds("K")


def test_a_range_is_inclusive_at_both_ends():
    shape = shape_of("physicalInterface", "activeIntensity")
    assert shape.holds(0)
    assert shape.holds(100)
    assert not shape.holds(-1)
    assert not shape.holds(120)


def test_a_boolean_field_rejects_an_integer():
    """isConnected is JSON true/false; a 1 would mean the shape has moved."""
    shape = shape_of("latestTelemetry", "isConnected")
    assert shape.holds(True)
    assert not shape.holds(1)


def test_a_flag_rejects_a_boolean():
    assert not shape_of("physicalInterface", "lockout").holds(True)
    assert shape_of("physicalInterface", "lockout").holds(0)


def test_a_bounded_field_uses_the_devices_own_limits():
    shape = shape_of("targetHeat", "setpoint")
    body = {"lockoutMin": 5, "lockoutMax": 24}

    assert shape.holds(5, body)
    assert shape.holds(24, body)
    assert not shape.holds(4, body)
    assert not shape.holds(30, body)


def test_a_bounded_field_without_limits_accepts_anything():
    """Absent bounds are not an excuse to invent them."""
    assert shape_of("targetHeat", "setpoint").holds(99, {})


def test_none_is_never_a_shape_violation():
    """An absent value is a missing field, reported separately."""
    for shape in SHAPES.values():
        assert shape.holds(None)


def test_an_unshaped_field_has_no_shape():
    assert shape_of("identity", "fw") is None
    assert shape_of("bbConfig", "pidFastKd") is None
    # Reported as 5 and 500, so not percentages.
    assert shape_of("physicalInterface", "darkRoomLevel") is None
    assert shape_of("physicalInterface", "brightRoomLevel") is None


def test_describe_names_the_expectation():
    assert "one of" in shape_of("modes", "mode").describe()
    assert shape_of("physicalInterface", "activeIntensity").describe() == "0-100"
    assert shape_of("targetHeat", "setpoint").describe(
        {"lockoutMin": 5, "lockoutMax": 24}
    ) == "5-24"


def test_a_non_numeric_value_fails_a_range():
    assert not Shape(low=0, high=100).holds("high")


def test_the_ambient_offset_range_matches_the_declaration():
    """Observed at 1 and -1.5; the capability document declares -5 to 5."""
    shape = shape_of("tracking", "ambientOffset")
    assert shape.holds(-1.5)
    assert shape.holds(5)
    assert not shape.holds(-6)
