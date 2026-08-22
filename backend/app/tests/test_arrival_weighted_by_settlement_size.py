"""Phase 15 follow-up — Primeira Chegada keeps happening after world
start, weighted by settlement size.

Before this: set_simulated_player_arrival_policy and
set_simulated_player_arrival_location_enabled were only ever called from
tests — no real campaign ever had an arrival policy or any eligible
arrival location, so transported people never arrived anywhere after the
initial 3. seed_initial_region now configures both, and selection is
weighted by Settlement.population_tier so bigger settlements draw
proportionally more new arrivals — small villages still get some, just
fewer.
"""

import random
from collections import Counter

from app.db.models.settlement import Settlement
from app.db.models.simulated_player_arrival import (
    SimulatedPlayerArrivalLocation,
    SimulatedPlayerArrivalPolicy,
)
from app.game.players.service import select_simulated_player_arrival_location
from app.game.world.seed import create_campaign, seed_initial_region


def test_seed_initial_region_configures_an_enabled_arrival_policy(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    seed_initial_region(db_session, campaign.id)

    policy = (
        db_session.query(SimulatedPlayerArrivalPolicy)
        .filter(SimulatedPlayerArrivalPolicy.campaign_id == campaign.id)
        .one()
    )

    assert policy.enabled is True
    assert policy.min_delay_minutes > 0
    assert policy.max_delay_minutes >= policy.min_delay_minutes
    assert policy.min_group_size >= 1
    assert policy.max_group_size >= policy.min_group_size


def test_every_major_settlement_and_the_starting_village_are_arrival_eligible(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)

    settlement_location_ids = {row[0] for row in db_session.query(Settlement.location_id).all()}
    enabled_location_ids = {
        row[0]
        for row in db_session.query(SimulatedPlayerArrivalLocation.location_id)
        .filter(SimulatedPlayerArrivalLocation.enabled.is_(True))
        .all()
    }

    assert village.id in enabled_location_ids
    # Every settlement (Tier 1 — has a Settlement row) is eligible; the
    # starting village's own new Settlement row (Phase 15 follow-up 2)
    # counts too.
    assert settlement_location_ids == enabled_location_ids


def test_minor_settlement_stubs_are_never_arrival_eligible(db_session):
    from app.db.models.location import Location

    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    minor_stub_ids = {
        row[0]
        for row in db_session.query(Location.id)
        .filter(Location.region_id == region.id, Location.materialization_tier == 2)
        .all()
    }
    enabled_location_ids = {
        row[0]
        for row in db_session.query(SimulatedPlayerArrivalLocation.location_id)
        .filter(SimulatedPlayerArrivalLocation.enabled.is_(True))
        .all()
    }

    assert minor_stub_ids.isdisjoint(enabled_location_ids)


def test_bigger_settlements_are_selected_proportionally_more_often(db_session):
    campaign = create_campaign(db_session, "Campanha A", world_seed=555)
    region, _village = seed_initial_region(db_session, campaign.id)

    settlements_by_location = {s.location_id: s for s in db_session.query(Settlement).all()}
    major_city_location_id = next(
        location_id
        for location_id, settlement in settlements_by_location.items()
        if settlement.settlement_type == "MAJOR_CITY"
    )
    hamlet_or_village_candidates = [
        location_id
        for location_id, settlement in settlements_by_location.items()
        if settlement.population_tier <= 2
    ]
    assert hamlet_or_village_candidates  # sanity: at least one small settlement exists

    rng = random.Random(1)
    picks = Counter()
    for _ in range(3000):
        location = select_simulated_player_arrival_location(db_session, campaign.id, rng=rng)
        picks[location.id] += 1

    major_city_picks = picks[major_city_location_id]
    small_settlement_average = sum(picks[loc_id] for loc_id in hamlet_or_village_candidates) / len(
        hamlet_or_village_candidates
    )

    assert major_city_picks > small_settlement_average
