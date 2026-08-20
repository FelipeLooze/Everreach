import json

import pytest

from app.core.enums import (
    CharacterAttributeKey,
    CombatActorType,
    CombatAwareness,
    CombatEncounterStatus,
    CombatTurnStatus,
    EventType,
)
from app.db.models.combat import CombatParticipant, CombatTurn
from app.db.models.event import WorldEvent
from app.db.models.npc import NPC
from app.game.attributes.service import get_character_attribute
from app.game.character.service import create_character
from app.game.combat.encounters import (
    CombatantSpec,
    add_participant,
    end_encounter,
    remove_participant,
    start_encounter,
)
from app.game.combat.turns import (
    CombatTurnError,
    complete_current_turn,
    get_current_turn,
    roll_initiative,
)
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign, seed_initial_region


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


def _setup(db_session):
    campaign = create_campaign(db_session, "Combat Turns")
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
    encounter = start_encounter(
        db_session,
        campaign.id,
        location.id,
        (
            CombatantSpec(CombatActorType.CHARACTER, character.id, "heroes"),
            CombatantSpec(
                CombatActorType.NPC,
                enemy.id,
                "bandits",
                awareness=CombatAwareness.SURPRISED,
            ),
        ),
    )
    return campaign, region, location, character, enemy, encounter


def test_initiative_uses_agility_and_awareness_and_is_persistently_idempotent(
    db_session,
):
    campaign, _region, _location, character, enemy, encounter = _setup(db_session)
    get_character_attribute(
        db_session,
        character.id,
        CharacterAttributeKey.AGILITY,
    ).value = 14

    order = roll_initiative(db_session, encounter, rng=SequenceRng(5, 20))

    hero = next(row for row in order if row.actor_id == character.id)
    bandit = next(row for row in order if row.actor_id == enemy.id)
    assert (hero.initiative_roll, hero.initiative_modifier, hero.initiative_score) == (
        5,
        2,
        7,
    )
    assert (
        bandit.initiative_roll,
        bandit.initiative_modifier,
        bandit.initiative_score,
    ) == (20, -5, 15)
    assert [row.id for row in order] == [bandit.id, hero.id]
    assert encounter.round_number == 1
    assert get_current_turn(db_session, encounter).participant_id == bandit.id

    replay = roll_initiative(db_session, encounter, rng=SequenceRng(1, 1))
    assert [row.id for row in replay] == [bandit.id, hero.id]
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_INITIATIVE_ROLLED.value)
        .count()
        == 1
    )
    payload = json.loads(
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_INITIATIVE_ROLLED.value)
        .one()
        .payload_json
    )
    assert payload["current_participant_id"] == bandit.id


def test_turn_advance_wraps_round_and_completion_retry_does_not_advance(db_session):
    _campaign, _region, _location, _character, _enemy, encounter = _setup(db_session)
    order = roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    first = order[0]
    second = order[1]

    result = complete_current_turn(
        db_session,
        encounter,
        first,
        completion_key="action:first",
    )
    assert result.replayed is False
    assert result.current_turn.participant_id == second.id
    replay = complete_current_turn(
        db_session,
        encounter,
        first,
        completion_key="action:first",
    )
    assert replay.replayed is True
    assert replay.current_turn.id == result.current_turn.id
    assert encounter.round_number == 1

    complete_current_turn(
        db_session,
        encounter,
        second,
        completion_key="action:second",
    )
    assert encounter.round_number == 2
    assert get_current_turn(db_session, encounter).participant_id == first.id
    assert db_session.query(CombatTurn).count() == 3
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_TURN_ADVANCED.value)
        .count()
        == 2
    )


def test_only_current_active_participant_can_complete_turn(db_session):
    _campaign, _region, _location, _character, _enemy, encounter = _setup(db_session)
    order = roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    with pytest.raises(CombatTurnError, match="Only the current"):
        complete_current_turn(
            db_session,
            encounter,
            order[1],
            completion_key="wrong-actor",
        )
    assert get_current_turn(db_session, encounter).participant_id == order[0].id


def test_late_arrival_is_appended_and_leaving_current_actor_is_skipped(db_session):
    campaign, region, location, _character, _enemy, encounter = _setup(db_session)
    order = roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    late_enemy = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Reforço",
        role="bandit",
        alive=True,
    )
    db_session.add(late_enemy)
    db_session.flush()

    late = add_participant(
        db_session,
        encounter,
        CombatantSpec(CombatActorType.NPC, late_enemy.id, "bandits"),
    )
    assert late.turn_order == 2
    assert late.initiative_roll is not None

    remove_participant(db_session, encounter, order[0], reason="fugiu")
    current = get_current_turn(db_session, encounter)
    assert current.participant_id == order[1].id
    skipped = (
        db_session.query(CombatTurn)
        .filter(CombatTurn.participant_id == order[0].id)
        .one()
    )
    assert skipped.status == CombatTurnStatus.SKIPPED.value


def test_ending_and_reset_close_and_remove_turn_history(db_session):
    campaign, _region, _location, _character, _enemy, encounter = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    end_encounter(
        db_session,
        encounter,
        CombatEncounterStatus.CANCELLED,
        reason="teste encerrado",
    )
    assert encounter.current_turn_order is None
    assert db_session.query(CombatTurn).one().status == CombatTurnStatus.SKIPPED.value

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(CombatTurn).count() == 0
    assert db_session.query(CombatParticipant).count() == 0


def test_last_active_participant_may_leave_without_creating_phantom_turn(db_session):
    _campaign, _region, _location, _character, _enemy, encounter = _setup(db_session)
    order = roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    remove_participant(db_session, encounter, order[1], reason="incapacitado")
    remove_participant(db_session, encounter, order[0], reason="fugiu")

    assert encounter.current_turn_order is None
    assert get_current_turn(db_session, encounter) is None
    assert (
        db_session.query(CombatTurn)
        .filter(CombatTurn.status == CombatTurnStatus.ACTIVE.value)
        .count()
        == 0
    )
