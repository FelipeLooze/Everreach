import random
from types import SimpleNamespace

from app.core.enums import (
    EventType,
    KnowledgeCertainty,
    KnowerType,
    RiskTolerance,
    SimulatedPlayerGoalType,
    SimulatedPlayerStatus,
)
from app.db.models.event import WorldEvent
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.location import LocationConnection
from app.db.models.memory import Memory
from app.db.models.relationship import SimulatedPlayerRelationship
from app.db.models.simulated_player import SimulatedPlayerSkill
from app.db.models.simulated_player_group import SimulatedPlayerGroup
from app.db.models.campaign import Campaign
from app.game.character.service import create_character
from app.game.npcs.service import teach_fact
from app.game.players.death import kill_simulated_player
from app.game.players.groups import (
    active_group_for_player,
    active_group_members,
    create_group,
    join_group,
    leave_group,
    start_group_travel,
)
from app.game.players.risk import acceptable_connections
from app.game.players.service import simulated_players_at_location
from app.game.relationships.service import record_simulated_players_interaction
from app.game.time.clock import advance_world_time, get_world_time
from app.game.world.seed import create_campaign, seed_initial_region
from app.game.world.reset import delete_campaign
from app.simulation import group_simulation, player_simulation, world_simulation


def _world(db_session):
    campaign = create_campaign(db_session, "Phase 7")
    region, village = seed_initial_region(db_session, campaign.id)
    players = simulated_players_at_location(db_session, village.id)
    return campaign, region, village, players


def test_risk_tolerance_filters_routes_before_selection(db_session):
    campaign, _region, _village, players = _world(db_session)
    cautious = players[0]
    cautious.risk_tolerance = RiskTolerance.CAUTIOUS.value
    connections = db_session.query(LocationConnection).filter(
        LocationConnection.from_location_id == cautious.location_id
    ).all()
    assert connections
    connections[0].danger = 1
    if len(connections) == 1:
        dangerous = SimpleNamespace(danger=5)
        choices = [connections[0], dangerous]
    else:
        connections[1].danger = 5
        choices = connections[:2]
    assert [route.danger for route in acceptable_connections(cautious, choices)] == [1]
    cautious.risk_tolerance = RiskTolerance.BOLD.value
    assert len(acceptable_connections(cautious, choices)) == 2


def test_training_advances_xp_mastery_level_and_renews_goal(db_session):
    campaign, _region, _village, players = _world(db_session)
    trainer = next(
        player for player in players if player.goal_type == SimulatedPlayerGoalType.TRAIN_SELF
    )
    for index in range(25):
        player_simulation._train(db_session, campaign.id, trainer, 540 + index * 60)

    skill = (
        db_session.query(SimulatedPlayerSkill)
        .filter(SimulatedPlayerSkill.simulated_player_id == trainer.id)
        .one()
    )
    assert trainer.level == 1
    assert trainer.xp == 25.0
    assert skill.name == "Sobrevivência"
    assert skill.mastery == 12.5
    assert trainer.goal_type == SimulatedPlayerGoalType.TRAIN_SELF
    assert trainer.goal_subject == "level:2"
    assert (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.actor_id == trainer.id,
            WorldEvent.event_type == EventType.SIMULATED_PLAYER_LEVELED_UP.value,
        )
        .count()
        == 1
    )


def test_gather_knowledge_goal_learns_local_fact_and_completes(db_session):
    campaign, _region, village, players = _world(db_session)
    social = next(
        player
        for player in players
        if player.goal_type == SimulatedPlayerGoalType.GATHER_KNOWLEDGE
    )
    from app.db.models.npc import NPC
    source = db_session.query(NPC).filter(NPC.location_id == village.id).first()
    fact = KnowledgeFact(
        campaign_id=campaign.id,
        fact_key="phase7_local_news",
        statement="Há marcas recentes perto da estrada.",
        social_priority=5,
    )
    db_session.add(fact)
    db_session.flush()
    teach_fact(
        db_session,
        campaign.id,
        fact.fact_key,
        KnowerType.NPC,
        source.id,
        certainty=KnowledgeCertainty.CONFIRMED,
    )

    result = player_simulation._process_player_opportunity(
        db_session,
        campaign.id,
        social,
        600,
        random.Random(1),
        1.0,
    )
    assert result.total_changes == 0
    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type == KnowerType.SIMULATED_PLAYER.value,
            KnowledgeKnower.knower_id == social.id,
        )
        .one_or_none()
        is not None
    )
    assert (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.actor_id == social.id,
            WorldEvent.event_type == EventType.SIMULATED_PLAYER_GOAL_COMPLETED.value,
        )
        .count()
        == 1
    )


def test_simulated_player_relationship_is_ordered_and_persistent(db_session):
    campaign, _region, _village, players = _world(db_session)
    first, second = players[:2]
    relationship = record_simulated_players_interaction(
        db_session,
        campaign.id,
        second.id,
        first.id,
        familiarity_delta=2,
        trust_delta=3,
    )
    repeated = record_simulated_players_interaction(
        db_session, campaign.id, first.id, second.id
    )
    assert repeated.id == relationship.id
    assert repeated.familiarity == 3
    assert repeated.trust == 3
    assert relationship.first_player_id < relationship.second_player_id
    assert db_session.query(SimulatedPlayerRelationship).count() == 1


def test_group_travel_moves_members_together(db_session):
    campaign, _region, village, players = _world(db_session)
    leader, companion = players[:2]
    group = create_group(
        db_session,
        campaign.id,
        leader,
        [companion],
        goal="Explorar juntos.",
    )
    third = players[2]
    join_group(db_session, group, third)
    assert len(active_group_members(db_session, group.id)) == 3
    leave_group(
        db_session,
        third.id,
        occurred_world_minute=get_world_time(db_session, campaign.id).total_minutes(),
    )
    assert len(active_group_members(db_session, group.id)) == 2
    connection = db_session.query(LocationConnection).filter(
        LocationConnection.from_location_id == leader.location_id
    ).first()
    assert connection is not None
    assert start_group_travel(
        db_session,
        group,
        connection,
        occurred_world_minute=get_world_time(db_session, campaign.id).total_minutes(),
    )
    assert leader.travel_arrival_world_minute == companion.travel_arrival_world_minute
    arrival = leader.travel_arrival_world_minute
    player_simulation._complete_travel_if_due(
        db_session, campaign.id, leader, arrival
    )
    player_simulation._complete_travel_if_due(
        db_session, campaign.id, companion, arrival
    )
    assert leader.location_id == companion.location_id == connection.to_location_id
    assert group.location_id == connection.to_location_id
    assert len(active_group_members(db_session, group.id)) == 2
    assert village.id != group.location_id


def test_relationship_can_form_group_during_daily_world_simulation(db_session):
    campaign, _region, _village, players = _world(db_session)
    first, second = players[:2]
    record_simulated_players_interaction(db_session, campaign.id, first.id, second.id)
    advance_world_time(db_session, campaign.id, 24 * 60)
    result = group_simulation.tick(db_session, campaign.id, 24 * 60)
    assert result.groups_formed == 1
    assert active_group_for_player(db_session, first.id) is not None
    assert active_group_for_player(db_session, second.id) is not None


def test_simulated_player_death_is_permanent_and_known_by_witnesses(db_session):
    campaign, region, village, players = _world(db_session)
    character = create_character(
        db_session, campaign.id, "Witness", region.id, village.id
    )
    victim, companion = players[:2]
    group = create_group(
        db_session, campaign.id, victim, [companion], goal="Stay together."
    )
    assert kill_simulated_player(
        db_session,
        campaign.id,
        victim,
        cause="ferimento mecânico fatal",
    )
    assert victim.status == SimulatedPlayerStatus.DEAD.value
    assert not kill_simulated_player(
        db_session, campaign.id, victim, cause="segunda tentativa"
    )
    assert active_group_for_player(db_session, victim.id) is None
    assert active_group_for_player(db_session, companion.id) is None
    assert group.status == "DISSOLVED"
    fact = (
        db_session.query(KnowledgeFact)
        .filter(KnowledgeFact.fact_key == f"simulated_player_death:{victim.id}")
        .one()
    )
    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id == character.id,
        )
        .one_or_none()
        is not None
    )
    assert (
        db_session.query(Memory)
        .filter(
            Memory.owner_type == "PLAYER",
            Memory.owner_id == character.id,
            Memory.subject == f"simulated_player:{victim.id}",
        )
        .one_or_none()
        is not None
    )
    advance_world_time(db_session, campaign.id, 60)
    player_simulation.tick(db_session, campaign.id, 60, rng=random.Random(1))
    assert victim.status == SimulatedPlayerStatus.DEAD.value


def test_several_days_of_world_tick_keep_phase_7_systems_consistent(
    db_session,
    monkeypatch,
):
    campaign, _region, _village, players = _world(db_session)
    record_simulated_players_interaction(
        db_session, campaign.id, players[0].id, players[1].id
    )
    monkeypatch.setattr(player_simulation, "ACTION_CHANCE_PER_HOUR", 1.0)
    elapsed = 3 * 24 * 60
    advance_world_time(db_session, campaign.id, elapsed)
    result = world_simulation.tick(
        db_session, campaign.id, elapsed, rng=random.Random(7)
    )
    trainer = next(
        player
        for player in players
        if player.goal_type == SimulatedPlayerGoalType.TRAIN_SELF
        or player.archetype == "TRAINER"
    )
    assert result.simulated_player_groups_formed == 1
    assert db_session.query(SimulatedPlayerGroup).count() == 1
    assert trainer.xp > 0 or trainer.level > 0
    assert get_world_time(db_session, campaign.id).day == 4


def test_campaign_delete_removes_all_phase_7_entities(db_session):
    campaign, _region, _village, players = _world(db_session)
    record_simulated_players_interaction(
        db_session, campaign.id, players[0].id, players[1].id
    )
    create_group(
        db_session,
        campaign.id,
        players[0],
        [players[1]],
        goal="Temporary group",
    )
    player_simulation._train(db_session, campaign.id, players[2], 600)
    assert delete_campaign(db_session, campaign.id)
    assert db_session.get(Campaign, campaign.id) is None
    assert db_session.query(SimulatedPlayerRelationship).count() == 0
    assert db_session.query(SimulatedPlayerGroup).count() == 0
    assert db_session.query(SimulatedPlayerSkill).count() == 0
