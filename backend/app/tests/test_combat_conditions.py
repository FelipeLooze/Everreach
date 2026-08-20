import pytest

from app.core.enums import (
    CombatActionType,
    CombatActorType,
    CombatConditionType,
    CombatEncounterStatus,
    CombatRangeBand,
    CombatTurnStatus,
    EventType,
)
from app.db.models.combat import CombatCondition, CombatParticipant, CombatTurn
from app.db.models.event import WorldEvent
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.combat.actions import resolve_attack
from app.game.combat.conditions import (
    CombatConditionError,
    active_conditions,
    apply_condition,
    remove_condition,
)
from app.game.combat.encounters import (
    CombatantSpec,
    end_encounter,
    remove_participant,
    start_encounter,
)
from app.game.combat.turns import get_current_turn, roll_initiative
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign, seed_initial_region


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


class FixedRng:
    def __init__(self, value: int):
        self.value = value

    def randint(self, _minimum: int, _maximum: int) -> int:
        return self.value


def _setup(db_session):
    campaign = create_campaign(db_session, "Combat Conditions")
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
        hp_current=30,
        hp_max=30,
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
                range_band=CombatRangeBand.ENGAGED,
            ),
        ),
    )
    participants = {
        row.actor_id: row
        for row in db_session.query(CombatParticipant)
        .filter(CombatParticipant.encounter_id == encounter.id)
        .all()
    }
    return (
        campaign,
        character,
        enemy,
        encounter,
        participants[character.id],
        participants[enemy.id],
    )


def test_condition_application_is_persistent_and_idempotent(db_session):
    campaign, _character, _enemy, encounter, hero, _bandit = _setup(db_session)

    first = apply_condition(
        db_session,
        encounter,
        hero,
        condition_type=CombatConditionType.WEAKENED,
        duration_turns=2,
        application_key="effect:weakness:1",
    )
    replay = apply_condition(
        db_session,
        encounter,
        hero,
        condition_type=CombatConditionType.WEAKENED,
        duration_turns=2,
        application_key="effect:weakness:1",
    )

    assert replay.replayed is True
    assert replay.condition.id == first.condition.id
    assert first.condition.applied_round == 0
    assert first.condition.remaining_turns == 2
    assert db_session.query(CombatCondition).count() == 1
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_CONDITION_APPLIED.value)
        .count()
        == 1
    )
    with pytest.raises(CombatConditionError, match="another condition"):
        apply_condition(
            db_session,
            encounter,
            hero,
            condition_type=CombatConditionType.EXPOSED,
            duration_turns=2,
            application_key="effect:weakness:1",
        )
    assert campaign.id == encounter.campaign_id


def test_weakened_and_exposed_modify_attack_and_expire_on_owner_turn(db_session):
    _campaign, _character, _enemy, encounter, hero, bandit = _setup(db_session)
    weakened = apply_condition(
        db_session,
        encounter,
        hero,
        condition_type=CombatConditionType.WEAKENED,
        duration_turns=1,
        application_key="weak-hero",
    ).condition
    exposed = apply_condition(
        db_session,
        encounter,
        bandit,
        condition_type=CombatConditionType.EXPOSED,
        duration_turns=1,
        application_key="exposed-bandit",
    ).condition
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    hero_action = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="condition-modifiers",
        rng=SequenceRng(10, 1),
    ).action

    assert hero_action.attack_modifier == -2
    assert hero_action.defense_modifier == -2
    assert hero_action.defense_total == 8
    assert weakened.active is False
    assert weakened.removal_reason == "duration_expired"
    assert exposed.active is True

    resolve_attack(
        db_session,
        encounter,
        bandit,
        hero,
        action_type=CombatActionType.RANGED_ATTACK,
        action_key="bandit-turn",
        rng=FixedRng(1),
    )
    assert exposed.active is False
    assert exposed.removal_reason == "duration_expired"


def test_stunned_skips_next_owner_turn_and_expires_automatically(db_session):
    _campaign, _character, _enemy, encounter, hero, bandit = _setup(db_session)
    stunned = apply_condition(
        db_session,
        encounter,
        hero,
        condition_type=CombatConditionType.STUNNED,
        duration_turns=1,
        application_key="stun-next-turn",
    ).condition
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    current = get_current_turn(db_session, encounter)

    assert current.participant_id == bandit.id
    assert stunned.active is False
    assert stunned.remaining_turns == 0
    skipped = (
        db_session.query(CombatTurn)
        .filter(CombatTurn.participant_id == hero.id)
        .one()
    )
    assert skipped.status == CombatTurnStatus.SKIPPED.value
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_CONDITION_TRIGGERED.value)
        .count()
        == 1
    )
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_CONDITION_EXPIRED.value)
        .count()
        == 1
    )


def test_manual_removal_and_invalid_duration_are_safe(db_session):
    _campaign, _character, _enemy, encounter, hero, _bandit = _setup(db_session)
    with pytest.raises(CombatConditionError, match="between 1 and 10"):
        apply_condition(
            db_session,
            encounter,
            hero,
            condition_type=CombatConditionType.EXPOSED,
            duration_turns=0,
            application_key="invalid-duration",
        )
    condition = apply_condition(
        db_session,
        encounter,
        hero,
        condition_type=CombatConditionType.EXPOSED,
        duration_turns=3,
        application_key="removable",
    ).condition

    remove_condition(db_session, encounter, condition, reason="efeito dissipado")
    remove_condition(db_session, encounter, condition, reason="retry")

    assert condition.active is False
    assert condition.removal_reason == "efeito dissipado"
    assert active_conditions(db_session, hero.id) == []
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_CONDITION_REMOVED.value)
        .count()
        == 1
    )


def test_participant_exit_and_encounter_end_remove_active_conditions(db_session):
    _campaign, _character, _enemy, encounter, hero, bandit = _setup(db_session)
    hero_condition = apply_condition(
        db_session,
        encounter,
        hero,
        condition_type=CombatConditionType.WEAKENED,
        duration_turns=2,
        application_key="hero-condition",
    ).condition
    bandit_condition = apply_condition(
        db_session,
        encounter,
        bandit,
        condition_type=CombatConditionType.EXPOSED,
        duration_turns=2,
        application_key="bandit-condition",
    ).condition

    remove_participant(db_session, encounter, bandit, reason="fugiu")
    assert bandit_condition.active is False
    assert bandit_condition.removal_reason.startswith("participant_left:")

    end_encounter(
        db_session,
        encounter,
        CombatEncounterStatus.CANCELLED,
        reason="sem oponente",
    )
    assert hero_condition.active is False
    assert hero_condition.removal_reason.startswith("encounter_ended:")


def test_campaign_reset_deletes_condition_history(db_session):
    campaign, _character, _enemy, encounter, hero, _bandit = _setup(db_session)
    apply_condition(
        db_session,
        encounter,
        hero,
        condition_type=CombatConditionType.WEAKENED,
        duration_turns=2,
        application_key="before-reset",
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(CombatCondition).count() == 0
