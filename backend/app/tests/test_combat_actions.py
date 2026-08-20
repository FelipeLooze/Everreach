import json

import pytest

from app.core.enums import (
    CharacterAttributeKey,
    CombatActionOutcome,
    CombatActionType,
    CombatActorType,
    CombatRangeBand,
    EventType,
)
from app.db.models.combat import CombatAction, CombatParticipant, CombatTurn
from app.db.models.event import WorldEvent
from app.db.models.npc import NPC
from app.game.attributes.service import get_character_attribute
from app.game.character.service import create_character
from app.game.combat.actions import CombatActionError, resolve_attack
from app.game.combat.encounters import CombatantSpec, start_encounter
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


def _setup(db_session):
    campaign = create_campaign(db_session, "Combat Actions")
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
        region,
        location,
        character,
        enemy,
        encounter,
        participants[character.id],
        participants[enemy.id],
    )


def test_melee_attack_uses_strength_resolves_hit_and_advances_turn(db_session):
    (
        _campaign,
        _region,
        _location,
        character,
        _enemy,
        encounter,
        hero,
        bandit,
    ) = _setup(db_session)
    get_character_attribute(
        db_session,
        character.id,
        CharacterAttributeKey.STRENGTH,
    ).value = 14
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    result = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="round-1:hero-melee",
        rng=FixedRng(8),
    )

    assert result.replayed is False
    assert result.action.attack_attribute == CharacterAttributeKey.STRENGTH.value
    assert result.action.attack_modifier == 2
    assert result.action.attack_total == 10
    assert result.action.defense_total == 10
    assert result.action.outcome == CombatActionOutcome.HIT.value
    assert get_current_turn(db_session, encounter).participant_id == bandit.id
    event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_ACTION_RESOLVED.value)
        .one()
    )
    payload = json.loads(event.payload_json)
    assert payload["action_id"] == result.action.id
    assert payload["outcome"] == CombatActionOutcome.HIT.value


def test_ranged_attack_uses_agility_and_engaged_penalty(db_session):
    (
        _campaign,
        _region,
        _location,
        character,
        _enemy,
        encounter,
        hero,
        bandit,
    ) = _setup(db_session)
    get_character_attribute(
        db_session,
        character.id,
        CharacterAttributeKey.AGILITY,
    ).value = 14
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.RANGED_ATTACK,
        action_key="engaged-shot",
        rng=FixedRng(9),
    ).action

    assert action.attack_attribute == CharacterAttributeKey.AGILITY.value
    assert action.attack_modifier == 0
    assert action.attack_total == 9
    assert action.outcome == CombatActionOutcome.MISS.value


@pytest.mark.parametrize(
    ("roll", "expected"),
    [
        (1, CombatActionOutcome.CRITICAL_MISS),
        (20, CombatActionOutcome.CRITICAL_HIT),
    ],
)
def test_natural_attack_extremes_override_totals(db_session, roll, expected):
    (
        _campaign,
        _region,
        _location,
        _character,
        _enemy,
        encounter,
        hero,
        bandit,
    ) = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key=f"natural-{roll}",
        rng=FixedRng(roll),
    ).action

    assert action.outcome == expected.value


def test_attack_rejects_wrong_turn_ally_and_invalid_range(db_session):
    (
        _campaign,
        _region,
        _location,
        _character,
        _enemy,
        encounter,
        hero,
        bandit,
    ) = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    with pytest.raises(CombatActionError, match="current participant"):
        resolve_attack(
            db_session,
            encounter,
            bandit,
            hero,
            action_type=CombatActionType.RANGED_ATTACK,
            action_key="wrong-turn",
            rng=FixedRng(10),
        )

    bandit.side_key = hero.side_key
    with pytest.raises(CombatActionError, match="own side"):
        resolve_attack(
            db_session,
            encounter,
            hero,
            bandit,
            action_type=CombatActionType.MELEE_ATTACK,
            action_key="friendly-fire",
            rng=FixedRng(10),
        )
    bandit.side_key = "bandits"
    bandit.range_band = CombatRangeBand.FAR.value
    with pytest.raises(CombatActionError, match="engaged target"):
        resolve_attack(
            db_session,
            encounter,
            hero,
            bandit,
            action_type=CombatActionType.MELEE_ATTACK,
            action_key="too-far",
            rng=FixedRng(10),
        )
    assert db_session.query(CombatAction).count() == 0


def test_attack_retry_returns_same_result_without_roll_or_second_advance(db_session):
    (
        _campaign,
        _region,
        _location,
        _character,
        _enemy,
        encounter,
        hero,
        bandit,
    ) = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    first = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="stable-action",
        rng=FixedRng(13),
    )
    current_after_first = get_current_turn(db_session, encounter)

    replay = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="stable-action",
        rng=FixedRng(1),
    )

    assert replay.replayed is True
    assert replay.action.id == first.action.id
    assert replay.action.attack_roll == 13
    assert get_current_turn(db_session, encounter).id == current_after_first.id
    assert db_session.query(CombatAction).count() == 1
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_ACTION_RESOLVED.value)
        .count()
        == 1
    )


def test_character_agility_contributes_to_defense_against_npc(db_session):
    (
        _campaign,
        _region,
        _location,
        character,
        _enemy,
        encounter,
        hero,
        bandit,
    ) = _setup(db_session)
    get_character_attribute(
        db_session,
        character.id,
        CharacterAttributeKey.AGILITY,
    ).value = 14
    hero.range_band = CombatRangeBand.ENGAGED.value
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))

    action = resolve_attack(
        db_session,
        encounter,
        bandit,
        hero,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="npc-attacks-hero",
        rng=FixedRng(12),
    ).action

    assert action.attack_modifier == 0
    assert action.defense_modifier == 2
    assert action.defense_total == 12
    assert action.outcome == CombatActionOutcome.HIT.value


def test_campaign_reset_removes_actions_before_turns(db_session):
    (
        campaign,
        _region,
        _location,
        _character,
        _enemy,
        encounter,
        hero,
        bandit,
    ) = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="before-reset",
        rng=FixedRng(10),
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(CombatAction).count() == 0
    assert db_session.query(CombatTurn).count() == 0
