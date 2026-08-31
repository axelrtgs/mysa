"""Criticality of semantic field names."""

from __future__ import annotations

from pymysa.fields import CRITICAL, IMPORTANT, Criticality, criticality


def test_the_climate_entity_essentials_are_critical():
    for name in ("current_temperature", "target_temperature", "mode", "connected"):
        assert criticality(name) is Criticality.CRITICAL


def test_a_lost_control_is_important_not_critical():
    """The device still heats without its display brightness."""
    for name in ("brightness", "lock", "fan_speed", "energy"):
        assert criticality(name) is Criticality.IMPORTANT


def test_an_unmapped_field_is_informational():
    assert criticality(None) is Criticality.INFORMATIONAL
    assert criticality("pidFastKd") is Criticality.INFORMATIONAL


def test_no_name_is_both_critical_and_important():
    assert not CRITICAL & IMPORTANT
