import random
from types import SimpleNamespace
from app.core.enums import (
    EventType,
    SimulatedPlayerActivity,
    SimulatedPlayerArchetype,
    SimulatedPlayerGoalType,
)
from app.db.models.event import WorldEvent
from app.game.world.seed import (
    create_campaign, 
    seed_initial_region,
)
from app.simulation import player_simulation
from app.game.time.clock import (
    advance_world_time,
    get_world_time,
)
from app.game.players.service import simulated_players_at_location
from app.simulation.player_simulation import (
    _hour_boundaries_crossed,
)

def test_explorer_prefers_unvisited_known_destination(
    monkeypatch,
):
    player = SimpleNamespace(
        archetype=SimulatedPlayerArchetype.EXPLORER,
        goal_type=SimulatedPlayerGoalType.NONE,
    )

    visited_connection = SimpleNamespace(
        to_location_id="visited",
        danger=1,
    )

    unvisited_connection = SimpleNamespace(
        to_location_id="unvisited",
        danger=1,
    )

    monkeypatch.setattr(
        player_simulation,
        "_visited_location_ids",
        lambda db, campaign_id, player: {
            "origin",
            "visited",
        },
    )

    selected = (
        player_simulation._select_travel_connection(
            None,
            "campaign_test",
            player,
            [
                visited_connection,
                unvisited_connection,
            ],
            random.Random(0),
        )
    )

    assert selected is unvisited_connection

def test_explore_region_goal_prioritizes_target_region(
    monkeypatch,
):
    player = SimpleNamespace(
        archetype=SimulatedPlayerArchetype.EXPLORER,
        goal_type=SimulatedPlayerGoalType.EXPLORE_REGION,
        goal_subject="region:target_region",
    )

    outside_region = SimpleNamespace(
        to_location_id="outside",
        danger=1,
    )

    target_region = SimpleNamespace(
        to_location_id="target",
        danger=1,
    )

    monkeypatch.setattr(
        player_simulation,
        "_visited_location_ids",
        lambda db, campaign_id, player: {
            "origin",
        },
    )

    monkeypatch.setattr(
        player_simulation,
        "_unvisited_connections_in_region",
        lambda db, connections, visited_location_ids, region_id: (
            [target_region]
            if region_id == "target_region"
            else []
        ),
    )

    selected = (
        player_simulation._select_travel_connection(
            None,
            "campaign_test",
            player,
            [
                outside_region,
                target_region,
            ],
            random.Random(0),
        )
    )

    assert selected is target_region

def test_explore_region_goal_completion_clears_goal_and_logs_event(
    db_session,
    monkeypatch,
):
    campaign = create_campaign(
        db_session,
        "Goal Completion",
    )

    _region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        village.id,
    )

    explorer = next(
        player
        for player in players
        if (
            player.goal_type
            == SimulatedPlayerGoalType.EXPLORE_REGION
        )
    )

    original_goal = explorer.goal

    monkeypatch.setattr(
        player_simulation,
        "_explore_region_goal_is_complete",
        lambda db, campaign_id, player, region_id: True,
    )

    completed = (
        player_simulation._complete_goal_if_satisfied(
            db_session,
            campaign.id,
            explorer,
            600,
        )
    )

    db_session.flush()

    assert completed is True

    assert explorer.goal_type == SimulatedPlayerGoalType.GATHER_KNOWLEDGE
    assert explorer.goal_subject == f"location:{village.id}"
    assert explorer.goal != original_goal

    event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id
            == campaign.id,
            WorldEvent.event_type
            == EventType.SIMULATED_PLAYER_GOAL_COMPLETED.value,
            WorldEvent.actor_type
            == "simulated_player",
            WorldEvent.actor_id
            == explorer.id,
        )
        .one()
    )

    assert event.world_minute == 600

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

def test_transportee_rests_at_night_and_wakes_at_six(
    db_session,
    monkeypatch,
):
    campaign = create_campaign(
        db_session,
        "Transported Rest Cycle",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    trainer = next(
        player
        for player in players
        if player.archetype
        == SimulatedPlayerArchetype.TRAINER
    )

    world_time = get_world_time(
        db_session,
        campaign.id,
    )

    world_time.hour = 21
    world_time.minute = 0

    trainer.activity = (
        SimulatedPlayerActivity.AVAILABLE.value
    )

    db_session.flush()

    monkeypatch.setattr(
        player_simulation,
        "ACTION_CHANCE_PER_HOUR",
        1.0,
    )

    # 21:00 -> 22:00.
    # At 22:00 the trainer must rest instead of training.
    advance_world_time(
        db_session,
        campaign.id,
        60,
    )

    night_result = player_simulation.tick(
        db_session,
        campaign.id,
        60,
        rng=random.Random(123),
    )

    assert night_result.trained == 0

    assert (
        trainer.activity
        == SimulatedPlayerActivity.RESTING.value
    )

    # 22:00 -> 06:00.
    # Every opportunity before 06:00 is resting.
    # At exactly 06:00 the trainer becomes available and may act.
    advance_world_time(
        db_session,
        campaign.id,
        480,
    )

    morning_result = player_simulation.tick(
        db_session,
        campaign.id,
        480,
        rng=random.Random(123),
    )

    assert morning_result.trained == 1

    assert (
        trainer.activity
        == SimulatedPlayerActivity.TRAINING.value
    )


def test_rest_state_syncs_without_hour_boundary(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Short Rest Tick",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    trainer = next(
        player
        for player in players
        if player.archetype
        == SimulatedPlayerArchetype.TRAINER
    )

    world_time = get_world_time(
        db_session,
        campaign.id,
    )

    world_time.hour = 22
    world_time.minute = 10

    trainer.activity = (
        SimulatedPlayerActivity.AVAILABLE.value
    )

    db_session.flush()

    # 22:10 -> 22:20 crosses no hourly action boundary.
    advance_world_time(
        db_session,
        campaign.id,
        10,
    )

    result = player_simulation.tick(
        db_session,
        campaign.id,
        10,
        rng=random.Random(123),
    )

    assert result.trained == 0

    assert (
        trainer.activity
        == SimulatedPlayerActivity.RESTING.value
    )


def test_rest_sync_does_not_change_local_activity_while_traveling():
    player = SimpleNamespace(
        activity=SimulatedPlayerActivity.AVAILABLE.value,
        travel_arrival_world_minute=23 * 60,
    )

    player_simulation._sync_rest_activity(
        player,
        22 * 60,
    )

    assert (
        player.activity
        == SimulatedPlayerActivity.AVAILABLE.value
    )

def test_train_self_goal_overrides_social_archetype(
    db_session,
    monkeypatch,
):
    campaign = create_campaign(
        db_session,
        "Goal Driven Training",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    social = next(
        player
        for player in players
        if player.archetype
        == SimulatedPlayerArchetype.SOCIAL
    )

    social.goal_type = (
        SimulatedPlayerGoalType.TRAIN_SELF
    )

    social.activity = (
        SimulatedPlayerActivity.AVAILABLE.value
    )

    db_session.flush()

    monkeypatch.setattr(
        player_simulation,
        "ACTION_CHANCE_PER_HOUR",
        1.0,
    )

    advance_world_time(
        db_session,
        campaign.id,
        60,
    )

    player_simulation.tick(
        db_session,
        campaign.id,
        60,
        rng=random.Random(123),
    )

    training_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type
            == EventType.SIMULATED_PLAYER_TRAINED.value,
            WorldEvent.actor_id == social.id,
        )
        .all()
    )

    assert len(training_events) == 1

    assert (
        social.activity
        == SimulatedPlayerActivity.TRAINING.value
    )

def test_gather_knowledge_goal_does_not_fall_back_to_training(
    db_session,
    monkeypatch,
):
    campaign = create_campaign(
        db_session,
        "Knowledge Goal Priority",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    trainer = next(
        player
        for player in players
        if player.archetype
        == SimulatedPlayerArchetype.TRAINER
    )

    trainer.goal_type = (
        SimulatedPlayerGoalType.GATHER_KNOWLEDGE
    )

    trainer.activity = (
        SimulatedPlayerActivity.AVAILABLE.value
    )

    db_session.flush()

    monkeypatch.setattr(
        player_simulation,
        "ACTION_CHANCE_PER_HOUR",
        1.0,
    )

    advance_world_time(
        db_session,
        campaign.id,
        60,
    )

    player_simulation.tick(
        db_session,
        campaign.id,
        60,
        rng=random.Random(123),
    )

    training_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type
            == EventType.SIMULATED_PLAYER_TRAINED.value,
            WorldEvent.actor_id == trainer.id,
        )
        .all()
    )

    assert training_events == []

    assert (
        trainer.activity
        == SimulatedPlayerActivity.AVAILABLE.value
    )

def test_temporary_training_continues_until_its_end(
    db_session,
    monkeypatch,
):
    campaign = create_campaign(
        db_session,
        "Temporary Training",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    social = next(
        player
        for player in players
        if player.archetype
        == SimulatedPlayerArchetype.SOCIAL
    )

    start_world_minute = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    social.activity = (
        SimulatedPlayerActivity.TRAINING.value
    )
    social.activity_until_world_minute = (
        start_world_minute + 180
    )

    db_session.flush()

    # An existing routine must not need a new random action roll.
    monkeypatch.setattr(
        player_simulation,
        "ACTION_CHANCE_PER_HOUR",
        0.0,
    )

    advance_world_time(
        db_session,
        campaign.id,
        120,
    )

    result = player_simulation.tick(
        db_session,
        campaign.id,
        120,
        rng=random.Random(123),
    )

    assert result.trained == 2

    assert (
        social.activity
        == SimulatedPlayerActivity.TRAINING.value
    )

    assert (
        social.activity_until_world_minute
        == start_world_minute + 180
    )

def test_temporary_activity_ends_without_hour_boundary(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Temporary Activity Ending",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    social = next(
        player
        for player in players
        if player.archetype
        == SimulatedPlayerArchetype.SOCIAL
    )

    start_world_minute = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    social.activity = (
        SimulatedPlayerActivity.TRAINING.value
    )
    social.activity_until_world_minute = (
        start_world_minute + 30
    )

    db_session.flush()

    # 08:00 -> 08:45.
    # No hourly opportunity occurs, but the routine ended at 08:30.
    advance_world_time(
        db_session,
        campaign.id,
        45,
    )

    result = player_simulation.tick(
        db_session,
        campaign.id,
        45,
        rng=random.Random(123),
    )

    assert result.trained == 0

    assert (
        social.activity
        == SimulatedPlayerActivity.AVAILABLE.value
    )

    assert social.activity_until_world_minute is None

def test_rest_cancels_temporary_local_activity(
    db_session,
    monkeypatch,
):
    campaign = create_campaign(
        db_session,
        "Rest Overrides Temporary Activity",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    social = next(
        player
        for player in players
        if player.archetype
        == SimulatedPlayerArchetype.SOCIAL
    )

    world_time = get_world_time(
        db_session,
        campaign.id,
    )

    world_time.hour = 21
    world_time.minute = 0

    start_world_minute = world_time.total_minutes()

    social.activity = (
        SimulatedPlayerActivity.TRAINING.value
    )
    social.activity_until_world_minute = (
        start_world_minute + 180
    )

    db_session.flush()

    monkeypatch.setattr(
        player_simulation,
        "ACTION_CHANCE_PER_HOUR",
        1.0,
    )

    advance_world_time(
        db_session,
        campaign.id,
        60,
    )

    result = player_simulation.tick(
        db_session,
        campaign.id,
        60,
        rng=random.Random(123),
    )

    assert result.trained == 0

    assert (
        social.activity
        == SimulatedPlayerActivity.RESTING.value
    )

    assert social.activity_until_world_minute is None

def test_starting_travel_cancels_temporary_local_activity(
    monkeypatch,
):
    connection = SimpleNamespace(
        id="connection_test",
        from_location_id="origin",
        to_location_id="destination",
    )

    player = SimpleNamespace(
        id="simulated_player_test",
        location_id="origin",
        archetype=SimulatedPlayerArchetype.EXPLORER,
        goal_type=SimulatedPlayerGoalType.NONE,
        goal_subject=None,
        activity=SimulatedPlayerActivity.TRAINING.value,
        activity_until_world_minute=9999,
        travel_connection_id=None,
        travel_destination_id=None,
        travel_started_world_minute=None,
        travel_arrival_world_minute=None,
    )

    monkeypatch.setattr(
        player_simulation,
        "_known_outgoing_connections",
        lambda db, campaign_id, player: [
            connection
        ],
    )

    monkeypatch.setattr(
        player_simulation,
        "_select_travel_connection",
        lambda db, campaign_id, player, connections, r: (
            connection
        ),
    )

    monkeypatch.setattr(
        player_simulation,
        "calculate_travel_minutes",
        lambda connection: 60,
    )

    monkeypatch.setattr(
        player_simulation,
        "log_event",
        lambda *args, **kwargs: None,
    )

    started = player_simulation._try_start_travel(
        None,
        "campaign_test",
        player,
        random.Random(123),
        1000,
    )

    assert started is True

    assert (
        player.activity
        == SimulatedPlayerActivity.AVAILABLE.value
    )

    assert player.activity_until_world_minute is None

    assert (
        player.travel_connection_id
        == connection.id
    )

    assert (
        player.travel_destination_id
        == connection.to_location_id
    )
