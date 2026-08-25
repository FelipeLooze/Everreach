"""Simplification Pass S1.1 — Lazy long-gap world catch-up.

Confirmed by the S0 audit: player_simulation.tick()'s DETAILED-tier hourly
opportunity loop previously replayed one iteration per (hour crossed ×
co-located simulated player), synchronously, inside whatever single player
action advanced the world clock far enough — a 60-day gap meant 1,440
iterations per detailed-tier player. Above LONG_GAP_BOUNDARY_THRESHOLD,
_detailed_opportunity_schedule now compresses the schedule using the exact
same "at least one action across N compressed hours" technique the
RELEVANT tier already used unconditionally — not new statistics, the
existing ones applied to the tier that previously never needed them.
"""
import random
import time

from app.core.enums import (
    EventType,
    SimulatedPlayerActivity,
    SimulatedPlayerArchetype,
    SimulatedPlayerStatus,
)
from app.db.models.event import WorldEvent
from app.db.models.simulated_player import SimulatedPlayer
from app.game.time.clock import advance_world_time, get_world_time
from app.game.world.seed import create_campaign, seed_initial_region
from app.simulation import player_simulation
from app.simulation.player_simulation import (
    ACTION_CHANCE_PER_HOUR,
    LONG_GAP_BOUNDARY_THRESHOLD,
    _aggregated_action_chance,
    _detailed_opportunity_schedule,
)

_HOUR = 60
_DAY = 24 * _HOUR


# --- schedule computation, unit-level ---


def test_short_gap_uses_the_unchanged_exact_schedule():
    # A 2-hour gap is far below the threshold — this must be byte-for-byte
    # today's pre-S1.1 behavior.
    opportunities, chance = _detailed_opportunity_schedule(1000 * _HOUR, 2 * _HOUR)
    assert len(opportunities) == 2
    assert chance == ACTION_CHANCE_PER_HOUR


def test_gap_exactly_at_the_threshold_still_uses_the_exact_schedule():
    minutes = LONG_GAP_BOUNDARY_THRESHOLD * _HOUR
    opportunities, chance = _detailed_opportunity_schedule(2000 * _HOUR, minutes)
    assert len(opportunities) == LONG_GAP_BOUNDARY_THRESHOLD
    assert chance == ACTION_CHANCE_PER_HOUR


def test_long_gap_schedule_is_bounded_by_the_threshold():
    minutes = 60 * _DAY  # the S0 audit's own worked example
    opportunities, chance = _detailed_opportunity_schedule(minutes, minutes)
    assert len(opportunities) <= LONG_GAP_BOUNDARY_THRESHOLD
    # Not just bounded — the point is that it no longer scales with gap
    # length at all beyond the threshold.
    assert len(opportunities) < 1440


def test_even_longer_gap_stays_within_the_same_bound():
    two_years_minutes = 2 * 365 * _DAY
    opportunities, _chance = _detailed_opportunity_schedule(
        two_years_minutes, two_years_minutes
    )
    assert len(opportunities) <= LONG_GAP_BOUNDARY_THRESHOLD


def test_long_gap_chance_is_calibrated_via_the_existing_aggregation_formula():
    # Must reuse _aggregated_action_chance (RELEVANT tier's own existing,
    # already-tested formula) rather than inventing a second one.
    minutes = 60 * _DAY
    _opportunities, chance = _detailed_opportunity_schedule(minutes, minutes)
    exact_count = len(
        player_simulation.boundary_minutes_crossed(minutes, minutes, 60)
    )
    expected_interval = 60 * -(-exact_count // LONG_GAP_BOUNDARY_THRESHOLD)
    assert chance == _aggregated_action_chance(expected_interval)


def test_raising_the_threshold_restores_exact_behavior_the_rollback_path():
    # The governing spec's own required rollback: a sufficiently high
    # threshold must fully restore today's exact-every-hour behavior.
    minutes = 60 * _DAY
    exact = player_simulation.boundary_minutes_crossed(minutes, minutes, 60)
    original = player_simulation.LONG_GAP_BOUNDARY_THRESHOLD
    player_simulation.LONG_GAP_BOUNDARY_THRESHOLD = 10**9
    try:
        opportunities, chance = _detailed_opportunity_schedule(minutes, minutes)
        assert opportunities == exact
        assert chance == ACTION_CHANCE_PER_HOUR
    finally:
        player_simulation.LONG_GAP_BOUNDARY_THRESHOLD = original


# --- full tick(), production-path ---


def _seed_and_force_training(db_session, name: str):
    campaign = create_campaign(db_session, name)
    _region, village = seed_initial_region(db_session, campaign.id)
    players = (
        db_session.query(SimulatedPlayer)
        .filter(
            SimulatedPlayer.campaign_id == campaign.id,
            SimulatedPlayer.status == SimulatedPlayerStatus.ACTIVE,
        )
        .all()
    )
    # Force every seeded simulated player into a state guaranteed to
    # produce a real, countable outcome (training) whenever an opportunity
    # succeeds, isolating the schedule/count behavior from goal/archetype
    # branching that isn't this test's concern.
    for player in players:
        player.activity = SimulatedPlayerActivity.AVAILABLE.value
        player.archetype = SimulatedPlayerArchetype.TRAINER
    db_session.flush()
    return campaign, village, players


def test_long_gap_tick_calls_process_opportunity_a_bounded_number_of_times(
    db_session, monkeypatch
):
    campaign, _village, players = _seed_and_force_training(
        db_session, "S1.1 Bounded Work"
    )
    call_count = {"n": 0}
    original = player_simulation._process_player_opportunity

    def _counting(*args, **kwargs):
        call_count["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        player_simulation, "_process_player_opportunity", _counting
    )

    advance_world_time(db_session, campaign.id, 60 * _DAY)
    player_simulation.tick(db_session, campaign.id, 60 * _DAY, rng=random.Random(1))

    # Bounded by threshold * (players actually in a scheduled tier), NOT by
    # the number of hours elapsed. The seeded village's starting population
    # is small (a handful of simulated players) — this assertion would fail
    # loudly (in the thousands) under the old unbounded behavior.
    assert call_count["n"] <= LONG_GAP_BOUNDARY_THRESHOLD * max(len(players), 1)
    assert call_count["n"] < 1440


def test_long_gap_produces_a_bounded_number_of_training_events_not_thousands(
    db_session, monkeypatch
):
    campaign, _village, players = _seed_and_force_training(
        db_session, "S1.1 Bounded Events"
    )
    # Force every opportunity to succeed, so the event count observed is
    # exactly the number of opportunities actually processed — the
    # strongest possible check that long gaps don't explode event volume.
    monkeypatch.setattr(player_simulation, "_aggregated_action_chance", lambda *_: 1.0)

    advance_world_time(db_session, campaign.id, 60 * _DAY)
    player_simulation.tick(db_session, campaign.id, 60 * _DAY, rng=random.Random(2))

    events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type == EventType.SIMULATED_PLAYER_TRAINED.value,
        )
        .count()
    )
    assert events <= LONG_GAP_BOUNDARY_THRESHOLD * max(len(players), 1)
    assert events < 1440


def test_long_gap_tick_is_fast_a_wall_clock_bound(db_session):
    campaign, _village, _players = _seed_and_force_training(
        db_session, "S1.1 Wall Clock"
    )
    advance_world_time(db_session, campaign.id, 365 * _DAY)
    started = time.monotonic()
    player_simulation.tick(db_session, campaign.id, 365 * _DAY, rng=random.Random(3))
    elapsed = time.monotonic() - started
    # A generous ceiling — this is a regression guard against the old
    # unbounded-iteration behavior (which would be ~8,760 opportunities for
    # a full year), not a tight performance benchmark.
    assert elapsed < 5.0


def test_world_time_remains_correct_after_a_long_gap_tick(db_session):
    campaign, _village, _players = _seed_and_force_training(
        db_session, "S1.1 World Time Correctness"
    )
    before = get_world_time(db_session, campaign.id).total_minutes()
    advance_world_time(db_session, campaign.id, 60 * _DAY)
    player_simulation.tick(db_session, campaign.id, 60 * _DAY, rng=random.Random(4))
    after = get_world_time(db_session, campaign.id).total_minutes()
    # Aggregation must never itself perturb the world clock — only the
    # ordinary advance_world_time call (already run above) does that.
    assert after == before + 60 * _DAY


def test_no_exception_or_corruption_on_a_very_large_elapsed_period(db_session):
    campaign, village, players = _seed_and_force_training(
        db_session, "S1.1 Extreme Gap"
    )
    advance_world_time(db_session, campaign.id, 5 * 365 * _DAY)
    result = player_simulation.tick(
        db_session, campaign.id, 5 * 365 * _DAY, rng=random.Random(5)
    )
    db_session.flush()
    assert result is not None
    # Every simulated player row must still be a coherent, readable record.
    for player in players:
        db_session.refresh(player)
        assert player.status == SimulatedPlayerStatus.ACTIVE.value


def test_short_gap_full_tick_behavior_is_unchanged_by_this_phase(
    db_session, monkeypatch
):
    # A direct regression guard: this exact scenario (2-hour gap, forced
    # 100% action chance) already has a pinned expected outcome in
    # test_player_simulation_time.py — re-asserting it here specifically
    # under S1.1's new code path confirms short gaps are untouched.
    campaign = create_campaign(db_session, "S1.1 Short Gap Unchanged")
    seed_initial_region(db_session, campaign.id)
    monkeypatch.setattr(player_simulation, "ACTION_CHANCE_PER_HOUR", 1.0)
    advance_world_time(db_session, campaign.id, 2 * _HOUR)
    result = player_simulation.tick(
        db_session, campaign.id, 2 * _HOUR, rng=random.Random(123)
    )
    assert result.trained == 2
