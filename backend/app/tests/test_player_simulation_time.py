import random

from app.core.enums import EventType
from app.db.models.event import WorldEvent
from app.game.world.seed import (
    create_campaign, 
    seed_initial_region,
)
from app.simulation import player_simulation
from app.game.time.clock import advance_world_time
from app.game.players.service import simulated_players_at_location
from app.simulation.player_simulation import (
    _hour_boundaries_crossed,
)

def test_traveling_simulated_player_is_not_physically_present_at_origin(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Presence",
    )

    _region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    players_before = simulated_players_at_location(
        db_session,
        village.id,
    )

    assert players_before

    traveling_player = players_before[0]
    traveling_player.travel_arrival_world_minute = 600

    db_session.flush()

    players_during_travel = simulated_players_at_location(
        db_session,
        village.id,
    )

    assert traveling_player.id not in {
        player.id
        for player in players_during_travel
    }

def test_no_hour_boundary_crossed(db_session):
    campaign = create_campaign(
        db_session,
        "Boundary Test",
    )

    db_session.flush()

    # 08:00 -> 08:30
    advance_world_time(
        db_session,
        campaign.id,
        30,
    )

    assert (
        _hour_boundaries_crossed(
            db_session,
            campaign.id,
            30,
        )
        == 0
    )


def test_one_hour_boundary_crossed(db_session):
    campaign = create_campaign(
        db_session,
        "Boundary Test",
    )

    db_session.flush()

    # 08:00 -> 09:00
    advance_world_time(
        db_session,
        campaign.id,
        60,
    )

    assert (
        _hour_boundaries_crossed(
            db_session,
            campaign.id,
            60,
        )
        == 1
    )


def test_multiple_hour_boundaries_crossed(db_session):
    campaign = create_campaign(
        db_session,
        "Boundary Test",
    )

    db_session.flush()

    # 08:00 -> 10:30
    advance_world_time(
        db_session,
        campaign.id,
        150,
    )

    assert (
        _hour_boundaries_crossed(
            db_session,
            campaign.id,
            150,
        )
        == 2
    )


def test_partitioned_time_crosses_same_number_of_boundaries(
    db_session,
):
    whole_campaign = create_campaign(
        db_session,
        "Whole Tick",
    )

    split_campaign = create_campaign(
        db_session,
        "Split Tick",
    )

    db_session.flush()

    # Cenário A:
    # 08:00 -> 10:00 de uma vez.
    advance_world_time(
        db_session,
        whole_campaign.id,
        120,
    )

    whole_opportunities = _hour_boundaries_crossed(
        db_session,
        whole_campaign.id,
        120,
    )

    # Cenário B:
    # 08:00 -> 09:00 -> 10:00.
    advance_world_time(
        db_session,
        split_campaign.id,
        60,
    )

    first_split = _hour_boundaries_crossed(
        db_session,
        split_campaign.id,
        60,
    )

    advance_world_time(
        db_session,
        split_campaign.id,
        60,
    )

    second_split = _hour_boundaries_crossed(
        db_session,
        split_campaign.id,
        60,
    )

    assert whole_opportunities == 2
    assert first_split + second_split == 2
    assert whole_opportunities == first_split + second_split

def test_player_simulation_behaves_the_same_for_whole_and_split_time(
    db_session,
    monkeypatch,
):
    whole_campaign = create_campaign(
        db_session,
        "Whole Simulation",
    )
    seed_initial_region(
        db_session,
        whole_campaign.id,
    )

    split_campaign = create_campaign(
        db_session,
        "Split Simulation",
    )
    seed_initial_region(
        db_session,
        split_campaign.id,
    )

    db_session.flush()

    # Toda oportunidade horária deve produzir ação.
    monkeypatch.setattr(
        player_simulation,
        "ACTION_CHANCE_PER_HOUR",
        1.0,
    )

    whole_rng = random.Random(123)
    split_rng = random.Random(123)

    # Cenário A:
    # 08:00 -> 10:00 em uma única passagem.
    advance_world_time(
        db_session,
        whole_campaign.id,
        120,
    )

    whole_result = player_simulation.tick(
        db_session,
        whole_campaign.id,
        120,
        rng=whole_rng,
    )

    assert whole_result.trained == 2

    # Cenário B:
    # 08:00 -> 09:00
    advance_world_time(
        db_session,
        split_campaign.id,
        60,
    )

    player_simulation.tick(
        db_session,
        split_campaign.id,
        60,
        rng=split_rng,
    )

    # 09:00 -> 10:00
    advance_world_time(
        db_session,
        split_campaign.id,
        60,
    )

    player_simulation.tick(
        db_session,
        split_campaign.id,
        60,
        rng=split_rng,
    )

    whole_training_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == whole_campaign.id,
            WorldEvent.event_type
            == EventType.SIMULATED_PLAYER_TRAINED.value,
        )
        .all()
    )

    split_training_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == split_campaign.id,
            WorldEvent.event_type
            == EventType.SIMULATED_PLAYER_TRAINED.value,
        )
        .all()
    )

    assert len(whole_training_events) == 2
    assert len(split_training_events) == 2