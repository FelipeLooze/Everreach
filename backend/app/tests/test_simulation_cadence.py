import pytest

from app.simulation.cadence import (
    boundaries_crossed,
    scheduled_occurrences_due,
)

DAY = 24 * 60
WEEK = 7 * DAY


def test_no_boundary_crossed():
    assert (
        boundaries_crossed(
            end_total_minutes=DAY - 1,
            elapsed_minutes=60,
            interval_minutes=DAY,
        )
        == 0
    )


def test_one_daily_boundary_crossed():
    assert (
        boundaries_crossed(
            end_total_minutes=DAY,
            elapsed_minutes=60,
            interval_minutes=DAY,
        )
        == 1
    )


def test_multiple_daily_boundaries_crossed():
    assert (
        boundaries_crossed(
            end_total_minutes=3 * DAY,
            elapsed_minutes=3 * DAY,
            interval_minutes=DAY,
        )
        == 3
    )


def test_weekly_boundary_is_not_daily():
    assert (
        boundaries_crossed(
            end_total_minutes=WEEK,
            elapsed_minutes=DAY,
            interval_minutes=WEEK,
        )
        == 1
    )

    assert (
        boundaries_crossed(
            end_total_minutes=WEEK - DAY,
            elapsed_minutes=DAY,
            interval_minutes=WEEK,
        )
        == 0
    )


def test_partitioning_does_not_change_boundary_count():
    whole = boundaries_crossed(
        end_total_minutes=7 * DAY,
        elapsed_minutes=7 * DAY,
        interval_minutes=DAY,
    )

    split = sum(
        boundaries_crossed(
            end_total_minutes=day * DAY,
            elapsed_minutes=DAY,
            interval_minutes=DAY,
        )
        for day in range(1, 8)
    )

    assert whole == split == 7


def test_zero_or_negative_elapsed_time_has_no_boundaries():
    assert boundaries_crossed(1000, 0, DAY) == 0
    assert boundaries_crossed(1000, -10, DAY) == 0


def test_invalid_interval_is_rejected():
    with pytest.raises(ValueError):
        boundaries_crossed(
            end_total_minutes=1000,
            elapsed_minutes=100,
            interval_minutes=0,
        )

def test_scheduled_occurrence_is_not_due_yet():
    assert (
        scheduled_occurrences_due(
            current_world_minute=999,
            next_update_world_minute=1000,
            interval_minutes=100,
        )
        == 0
    )


def test_scheduled_occurrence_is_due_exactly_now():
    assert (
        scheduled_occurrences_due(
            current_world_minute=1000,
            next_update_world_minute=1000,
            interval_minutes=100,
        )
        == 1
    )


def test_scheduled_occurrences_include_missed_intervals():
    assert (
        scheduled_occurrences_due(
            current_world_minute=1400,
            next_update_world_minute=1000,
            interval_minutes=100,
        )
        == 5
    )


def test_unscheduled_development_has_no_occurrences():
    assert (
        scheduled_occurrences_due(
            current_world_minute=5000,
            next_update_world_minute=None,
            interval_minutes=100,
        )
        == 0
    )


def test_invalid_scheduled_interval_is_rejected():
    with pytest.raises(ValueError):
        scheduled_occurrences_due(
            current_world_minute=1000,
            next_update_world_minute=1000,
            interval_minutes=0,
        )