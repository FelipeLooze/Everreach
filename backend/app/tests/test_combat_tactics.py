import json

import pytest

from app.core.enums import (
    CharacterAttributeKey,
    CombatActionType,
    CombatActorType,
    CombatConditionType,
    CombatEncounterStatus,
    CombatRangeBand,
    CombatTacticalActionType,
    EventType,
)
from app.db.models.combat import CombatCondition, CombatParticipant, CombatTacticalAction
from app.db.models.event import WorldEvent
from app.db.models.npc import NPC
from app.game.attributes.service import get_character_attribute
from app.game.character.service import create_character
from app.game.combat.actions import CombatActionError, resolve_attack
from app.game.combat.costs import CombatResourceError
from app.game.combat.encounters import CombatantSpec, start_encounter
from app.game.combat.tactics import CombatTacticalActionError, resolve_tactical_action
from app.game.combat.turns import get_current_turn, roll_initiative
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign, seed_initial_region


class FixedRng:
    def __init__(self, value: int):
        self.value = value

    def randint(self, _minimum: int, _maximum: int) -> int:
        return self.value


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


class ExplodingRng:
    def randint(self, _minimum: int, _maximum: int) -> int:
        raise AssertionError("A rejected action must not roll.")


def _setup(db_session, *, enemy_range=CombatRangeBand.ENGAGED):
    campaign = create_campaign(db_session, "Combat Tactics")
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
                range_band=enemy_range,
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


def test_guard_spends_once_grants_defense_and_expires_on_owner_turn(db_session):
    _campaign, character, enemy, encounter, hero, bandit = _setup(db_session)
    hero.range_band = CombatRangeBand.ENGAGED.value
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    guarded = resolve_tactical_action(
        db_session,
        encounter,
        hero,
        action_type=CombatTacticalActionType.GUARD,
        action_key="round-1:hero-guard",
    )

    assert character.stamina_current == 19
    assert guarded.action.resource_before == 20
    assert guarded.action.resource_after == 19
    assert guarded.condition is not None
    assert guarded.condition.condition_type == CombatConditionType.GUARDED.value
    assert guarded.condition.source_tactical_action_id == guarded.action.id
    attack = resolve_attack(
        db_session,
        encounter,
        bandit,
        hero,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="round-1:bandit-attack",
        rng=FixedRng(1),
    ).action
    assert attack.defense_modifier == 2
    assert attack.defense_total == 12
    assert guarded.condition.active is True

    follow_up = resolve_tactical_action(
        db_session,
        encounter,
        hero,
        action_type=CombatTacticalActionType.DODGE,
        action_key="round-2:hero-dodge",
    )
    assert guarded.condition.active is False
    assert follow_up.condition is not None
    assert follow_up.condition.condition_type == CombatConditionType.DODGING.value
    assert character.stamina_current == 17


def test_tactical_action_replay_is_idempotent_and_key_cannot_be_reused(db_session):
    _campaign, character, _enemy, encounter, hero, bandit = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    first = resolve_tactical_action(
        db_session,
        encounter,
        hero,
        action_type=CombatTacticalActionType.GUARD,
        action_key="stable-key",
    )
    replay = resolve_tactical_action(
        db_session,
        encounter,
        hero,
        action_type=CombatTacticalActionType.GUARD,
        action_key="stable-key",
    )

    assert replay.replayed is True
    assert replay.action.id == first.action.id
    assert replay.condition.id == first.condition.id
    assert character.stamina_current == 19
    assert db_session.query(CombatTacticalAction).count() == 1
    with pytest.raises(CombatTacticalActionError, match="another tactical action"):
        resolve_tactical_action(
            db_session,
            encounter,
            bandit,
            action_type=CombatTacticalActionType.GUARD,
            action_key="stable-key",
        )


@pytest.mark.parametrize(
    ("action_type", "start", "expected"),
    [
        (CombatTacticalActionType.APPROACH, CombatRangeBand.FAR, CombatRangeBand.NEAR),
        (CombatTacticalActionType.RETREAT, CombatRangeBand.NEAR, CombatRangeBand.FAR),
        (
            CombatTacticalActionType.DISENGAGE,
            CombatRangeBand.ENGAGED,
            CombatRangeBand.NEAR,
        ),
    ],
)
def test_tactical_movement_changes_one_range_band_and_persists_snapshot(
    db_session, action_type, start, expected
):
    _campaign, character, _enemy, encounter, hero, bandit = _setup(
        db_session,
        enemy_range=start,
    )
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_tactical_action(
        db_session,
        encounter,
        hero,
        target=bandit,
        action_type=action_type,
        action_key=f"move:{action_type.value.lower()}",
    ).action

    assert bandit.range_band == expected.value
    assert action.previous_range_band == start.value
    assert action.new_range_band == expected.value
    assert action.resource_cost == 1
    assert character.stamina_current == 19
    assert get_current_turn(db_session, encounter).participant_id == bandit.id


def test_invalid_movement_is_rejected_without_cost_or_turn_advance(db_session):
    _campaign, character, _enemy, encounter, hero, bandit = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    original_turn = get_current_turn(db_session, encounter)

    with pytest.raises(CombatTacticalActionError, match="already engaged"):
        resolve_tactical_action(
            db_session,
            encounter,
            hero,
            target=bandit,
            action_type=CombatTacticalActionType.APPROACH,
            action_key="invalid-approach",
        )

    assert character.stamina_current == 20
    assert get_current_turn(db_session, encounter).id == original_turn.id
    assert db_session.query(CombatTacticalAction).count() == 0


def test_failed_flee_spends_resource_keeps_actor_and_advances_turn(db_session):
    campaign, character, _enemy, encounter, hero, bandit = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    result = resolve_tactical_action(
        db_session,
        encounter,
        hero,
        action_type=CombatTacticalActionType.FLEE,
        action_key="hero-flee-fail",
        rng=FixedRng(1),
    )

    assert result.action.success is False
    assert result.action.roll == 1
    assert result.action.dc == 12
    assert character.stamina_current == 18
    assert hero.active is True
    assert encounter.status == CombatEncounterStatus.ACTIVE.value
    assert get_current_turn(db_session, encounter).participant_id == bandit.id
    event = (
        db_session.query(WorldEvent)
        .filter(EventType.COMBAT_TACTICAL_ACTION_RESOLVED.value == WorldEvent.event_type)
        .one()
    )
    assert json.loads(event.payload_json)["success"] is False
    assert event.campaign_id == campaign.id


def test_successful_character_flee_ends_encounter_and_replays_after_end(db_session):
    _campaign, character, _enemy, encounter, hero, _bandit = _setup(db_session)
    get_character_attribute(
        db_session,
        character.id,
        CharacterAttributeKey.AGILITY,
    ).value = 14
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    first = resolve_tactical_action(
        db_session,
        encounter,
        hero,
        action_type=CombatTacticalActionType.FLEE,
        action_key="hero-flee-success",
        rng=FixedRng(10),
    )
    replay = resolve_tactical_action(
        db_session,
        encounter,
        hero,
        action_type=CombatTacticalActionType.FLEE,
        action_key="hero-flee-success",
        rng=ExplodingRng(),
    )

    assert first.action.modifier == 2
    assert first.action.total == 12
    assert first.action.success is True
    assert hero.active is False
    assert encounter.status == CombatEncounterStatus.FLED.value
    assert encounter.current_turn_order is None
    assert replay.replayed is True
    assert replay.action.id == first.action.id
    assert character.stamina_current == 18


def test_successful_last_enemy_flee_resolves_victory(db_session):
    _campaign, _character, enemy, encounter, hero, bandit = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))

    action = resolve_tactical_action(
        db_session,
        encounter,
        bandit,
        action_type=CombatTacticalActionType.FLEE,
        action_key="bandit-flee-success",
        rng=FixedRng(20),
    ).action

    assert action.success is True
    assert enemy.stamina_current == 8
    assert bandit.active is False
    assert hero.active is False
    assert encounter.status == CombatEncounterStatus.VICTORY.value


def test_insufficient_stamina_rejects_before_roll_and_attack_after_tactic_is_blocked(
    db_session,
):
    _campaign, character, _enemy, encounter, hero, bandit = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    character.stamina_current = 1
    original_turn = get_current_turn(db_session, encounter)

    with pytest.raises(CombatResourceError, match="Insufficient stamina"):
        resolve_tactical_action(
            db_session,
            encounter,
            hero,
            action_type=CombatTacticalActionType.FLEE,
            action_key="too-tired",
            rng=ExplodingRng(),
        )
    assert get_current_turn(db_session, encounter).id == original_turn.id
    assert db_session.query(CombatTacticalAction).count() == 0

    character.stamina_current = 20
    resolve_tactical_action(
        db_session,
        encounter,
        hero,
        action_type=CombatTacticalActionType.GUARD,
        action_key="hero-acted",
    )
    with pytest.raises(CombatActionError, match="current participant"):
        resolve_attack(
            db_session,
            encounter,
            hero,
            bandit,
            action_type=CombatActionType.MELEE_ATTACK,
            action_key="hero-second-action",
            rng=ExplodingRng(),
        )


def test_campaign_reset_deletes_tactical_action_and_linked_condition(db_session):
    campaign, _character, _enemy, encounter, hero, _bandit = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    resolve_tactical_action(
        db_session,
        encounter,
        hero,
        action_type=CombatTacticalActionType.GUARD,
        action_key="before-reset",
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(CombatTacticalAction).count() == 0
    assert db_session.query(CombatCondition).count() == 0
