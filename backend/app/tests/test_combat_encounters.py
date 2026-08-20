import json

import pytest

from app.core.enums import (
    CombatActorType,
    CombatAwareness,
    CombatEncounterStatus,
    CombatRangeBand,
    EventType,
)
from app.db.models.combat import CombatEncounter, CombatParticipant
from app.db.models.event import WorldEvent
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.game.character.service import create_character, kill_character
from app.game.combat.encounters import (
    CombatantSpec,
    CombatEncounterError,
    add_participant,
    end_encounter,
    get_active_encounter_for_actor,
    list_active_participants,
    remove_participant,
    start_encounter,
)
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Combat Foundation")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    enemy = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Bandido",
        role="bandit",
        alive=True,
    )
    db_session.add(enemy)
    db_session.flush()
    return campaign, region, location, character, enemy


def _initial_specs(character, enemy):
    return (
        CombatantSpec(
            CombatActorType.CHARACTER,
            character.id,
            "protagonists",
            range_band=CombatRangeBand.NEAR,
        ),
        CombatantSpec(
            CombatActorType.NPC,
            enemy.id,
            "bandits",
            awareness=CombatAwareness.SURPRISED,
        ),
    )


def test_start_encounter_persists_concrete_sides_and_event(db_session):
    campaign, _region, location, character, enemy = _setup(db_session)

    encounter = start_encounter(
        db_session,
        campaign.id,
        location.id,
        _initial_specs(character, enemy),
    )

    assert encounter.status == CombatEncounterStatus.ACTIVE.value
    assert encounter.round_number == 0
    assert encounter.ended_world_minute is None
    participants = list_active_participants(db_session, encounter.id)
    assert {(row.actor_type, row.actor_id, row.side_key) for row in participants} == {
        (CombatActorType.CHARACTER.value, character.id, "protagonists"),
        (CombatActorType.NPC.value, enemy.id, "bandits"),
    }
    npc_participant = next(
        row for row in participants if row.actor_type == CombatActorType.NPC.value
    )
    assert npc_participant.awareness == CombatAwareness.SURPRISED.value
    event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_STARTED.value)
        .one()
    )
    assert json.loads(event.payload_json)["encounter_id"] == encounter.id
    assert (
        get_active_encounter_for_actor(
            db_session,
            CombatActorType.CHARACTER,
            character.id,
        )
        is encounter
    )


def test_encounter_rejects_one_side_duplicates_absent_and_dead_actors(db_session):
    campaign, region, location, character, enemy = _setup(db_session)
    duplicate = CombatantSpec(
        CombatActorType.CHARACTER,
        character.id,
        "same",
    )
    with pytest.raises(CombatEncounterError, match="duplicated"):
        start_encounter(
            db_session,
            campaign.id,
            location.id,
            (duplicate, duplicate),
        )
    with pytest.raises(CombatEncounterError, match="distinct sides"):
        start_encounter(
            db_session,
            campaign.id,
            location.id,
            (
                duplicate,
                CombatantSpec(CombatActorType.NPC, enemy.id, "same"),
            ),
        )

    distant = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id="missing_location",
        name="Distante",
        alive=True,
    )
    # Use a real but different seeded location to preserve foreign-key validity.
    other_location = (
        db_session.query(Location)
        .filter(
            Location.region_id == region.id,
            Location.id != location.id,
        )
        .first()
    )
    distant.location_id = other_location.id
    db_session.add(distant)
    db_session.flush()
    with pytest.raises(CombatEncounterError, match="living and present"):
        start_encounter(
            db_session,
            campaign.id,
            location.id,
            (
                duplicate,
                CombatantSpec(CombatActorType.NPC, distant.id, "enemy"),
            ),
        )

    kill_character(db_session, campaign.id, character, cause="test")
    with pytest.raises(CombatEncounterError, match="living and present"):
        start_encounter(
            db_session,
            campaign.id,
            location.id,
            _initial_specs(character, enemy),
        )


def test_actor_cannot_enter_two_active_encounters(db_session):
    campaign, region, location, character, enemy = _setup(db_session)
    start_encounter(
        db_session,
        campaign.id,
        location.id,
        _initial_specs(character, enemy),
    )
    second_enemy = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Segundo Bandido",
        alive=True,
    )
    db_session.add(second_enemy)
    db_session.flush()

    with pytest.raises(CombatEncounterError, match="already"):
        start_encounter(
            db_session,
            campaign.id,
            location.id,
            (
                CombatantSpec(
                    CombatActorType.CHARACTER,
                    character.id,
                    "protagonists",
                ),
                CombatantSpec(
                    CombatActorType.NPC,
                    second_enemy.id,
                    "bandits",
                ),
            ),
        )


def test_participant_can_join_and_leave_only_while_encounter_is_active(db_session):
    campaign, _region, location, character, enemy = _setup(db_session)
    encounter = start_encounter(
        db_session,
        campaign.id,
        location.id,
        _initial_specs(character, enemy),
    )
    ally = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Aliada",
        location_id=location.id,
    )
    db_session.add(ally)
    db_session.flush()

    participant = add_participant(
        db_session,
        encounter,
        CombatantSpec(
            CombatActorType.SIMULATED_PLAYER,
            ally.id,
            "protagonists",
            range_band=CombatRangeBand.FAR,
        ),
    )
    remove_participant(
        db_session,
        encounter,
        participant,
        reason="recuou para fora do confronto",
    )

    assert participant.active is False
    assert participant.left_world_minute is not None
    assert participant.left_reason == "recuou para fora do confronto"
    rejoined = add_participant(
        db_session,
        encounter,
        CombatantSpec(
            CombatActorType.SIMULATED_PLAYER,
            ally.id,
            "protagonists",
            range_band=CombatRangeBand.NEAR,
        ),
    )
    assert rejoined.id == participant.id
    assert rejoined.active is True
    assert rejoined.left_world_minute is None
    remove_participant(
        db_session,
        encounter,
        rejoined,
        reason="deixou o confronto definitivamente",
    )
    assert (
        get_active_encounter_for_actor(
            db_session,
            CombatActorType.SIMULATED_PLAYER,
            ally.id,
        )
        is None
    )


def test_end_encounter_is_terminal_idempotent_and_releases_participants(db_session):
    campaign, _region, location, character, enemy = _setup(db_session)
    encounter = start_encounter(
        db_session,
        campaign.id,
        location.id,
        _initial_specs(character, enemy),
    )

    ended = end_encounter(
        db_session,
        encounter,
        CombatEncounterStatus.VICTORY,
        reason="os inimigos se renderam",
    )
    repeated = end_encounter(
        db_session,
        encounter,
        CombatEncounterStatus.VICTORY,
        reason="os inimigos se renderam",
    )

    assert repeated is ended
    assert ended.ended_world_minute is not None
    assert list_active_participants(db_session, encounter.id) == []
    assert (
        get_active_encounter_for_actor(
            db_session,
            CombatActorType.CHARACTER,
            character.id,
        )
        is None
    )
    with pytest.raises(CombatEncounterError, match="already ended"):
        end_encounter(
            db_session,
            encounter,
            CombatEncounterStatus.DEFEAT,
            reason="resultado diferente",
        )
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_ENDED.value)
        .count()
        == 1
    )


def test_campaign_delete_removes_combat_foundation_rows(db_session):
    campaign, _region, location, character, enemy = _setup(db_session)
    start_encounter(
        db_session,
        campaign.id,
        location.id,
        _initial_specs(character, enemy),
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(CombatParticipant).count() == 0
    assert db_session.query(CombatEncounter).count() == 0
