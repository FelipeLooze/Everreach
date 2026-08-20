import random

from app.core.enums import (
    NPCActivity,
    SimulatedPlayerArchetype,
)
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.relationship import CharacterNPCRelationship
from app.game.character.service import create_character
from app.game.players.service import (
    set_abstract_simulated_player_population,
    simulated_players_at_location,
)
from app.game.time.clock import advance_world_time
from app.game.world.seed import create_campaign, seed_initial_region
from app.simulation import npc_simulation, player_simulation, world_simulation
from app.simulation.scope import SimulationTier, build_simulation_scope


def _running_world(db_session):
    campaign = create_campaign(db_session, "Layered Simulation")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        village.id,
    )
    remote = (
        db_session.query(Location)
        .filter(
            Location.region_id == region.id,
            Location.id != village.id,
        )
        .order_by(Location.id)
        .first()
    )
    assert remote is not None
    return campaign, character, village, remote


def test_scope_separates_detailed_relevant_and_abstract_entities(db_session):
    campaign, character, village, remote = _running_world(db_session)

    unknown_npc = NPC(
        campaign_id=campaign.id,
        region_id=remote.region_id,
        location_id=remote.id,
        name="Unknown remote resident",
    )
    known_npc = NPC(
        campaign_id=campaign.id,
        region_id=remote.region_id,
        location_id=remote.id,
        name="Known remote resident",
    )
    db_session.add_all([unknown_npc, known_npc])
    db_session.flush()
    db_session.add(
        CharacterNPCRelationship(
            campaign_id=campaign.id,
            character_id=character.id,
            npc_id=known_npc.id,
        )
    )
    set_abstract_simulated_player_population(
        db_session,
        campaign.id,
        remote.id,
        10_000,
    )

    scope = build_simulation_scope(db_session, campaign.id)

    assert scope.unrestricted is False
    assert scope.detailed_location_ids == frozenset({village.id})
    assert scope.npc_tier(unknown_npc.id, remote.id) == SimulationTier.ABSTRACT
    assert scope.npc_tier(known_npc.id, remote.id) == SimulationTier.RELEVANT
    assert scope.simulated_player_tier(remote.id) == SimulationTier.RELEVANT
    assert scope.abstract_simulated_players == 10_000
    assert scope.materialized_simulated_players == 3


def test_abstract_npc_routines_are_updated_in_bulk(db_session):
    campaign, _character, _village, remote = _running_world(db_session)
    remote_workers = [
        NPC(
            campaign_id=campaign.id,
            region_id=remote.region_id,
            location_id=remote.id,
            name=f"Remote worker {index}",
            role="ferreira",
            activity=NPCActivity.AVAILABLE.value,
        )
        for index in range(250)
    ]
    db_session.add_all(remote_workers)
    db_session.flush()

    advance_world_time(db_session, campaign.id, 10)
    result = npc_simulation.tick(db_session, campaign.id, 10)

    db_session.expire_all()
    remote_worker_count = (
        db_session.query(NPC)
        .filter(
            NPC.campaign_id == campaign.id,
            NPC.location_id == remote.id,
            NPC.role == "ferreira",
            NPC.activity == NPCActivity.WORKING.value,
        )
        .count()
    )
    assert remote_worker_count == 250
    assert result.changes >= 250


def test_relevant_distant_player_uses_aggregate_six_hour_cadence(
    db_session,
    monkeypatch,
):
    campaign, _character, village, remote = _running_world(db_session)
    trainer = next(
        player
        for player in simulated_players_at_location(db_session, village.id)
        if player.archetype == SimulatedPlayerArchetype.TRAINER
    )
    trainer.location_id = remote.id
    db_session.flush()
    monkeypatch.setattr(player_simulation, "ACTION_CHANCE_PER_HOUR", 1.0)

    # 08:00 -> 09:00: no six-hour boundary for a distant relevant person.
    advance_world_time(db_session, campaign.id, 60)
    first = player_simulation.tick(
        db_session,
        campaign.id,
        60,
        rng=random.Random(1),
    )
    assert first.trained == 0

    # 09:00 -> 12:00 crosses the 12:00 aggregate boundary exactly once.
    advance_world_time(db_session, campaign.id, 180)
    second = player_simulation.tick(
        db_session,
        campaign.id,
        180,
        rng=random.Random(1),
    )
    assert second.trained == 1


def test_world_tick_reports_abstract_population_without_materializing_it(
    db_session,
):
    campaign, _character, _village, remote = _running_world(db_session)
    set_abstract_simulated_player_population(
        db_session,
        campaign.id,
        remote.id,
        25_000,
    )
    materialized_before = build_simulation_scope(
        db_session,
        campaign.id,
    ).materialized_simulated_players

    advance_world_time(db_session, campaign.id, 1)
    result = world_simulation.tick(db_session, campaign.id, 1)

    assert result.abstract_simulated_players == 25_000
    assert result.materialized_simulated_players == materialized_before
    assert result.detailed_locations == 1
    assert (
        build_simulation_scope(db_session, campaign.id)
        .materialized_simulated_players
        == materialized_before
    )
