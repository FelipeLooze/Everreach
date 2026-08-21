import json

import pytest

from app.core.enums import (
    CharacterAttributeKey,
    CharacterStatus,
    CharacterResourceKey,
    CombatActionOutcome,
    CombatActionType,
    CombatActorType,
    CombatEncounterStatus,
    CombatRangeBand,
    EventType,
    SimulatedPlayerStatus,
)
from app.db.models.combat import CombatAction, CombatParticipant, CombatTurn
from app.db.models.event import WorldEvent
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.game.attributes.service import get_character_attribute
from app.game.character.service import create_character
from app.game.combat.actions import CombatActionError, resolve_attack
from app.game.combat.costs import CombatResourceError
from app.game.combat.encounters import CombatantSpec, start_encounter
from app.game.combat.turns import get_current_turn, roll_initiative
from app.game.inventory.service import add_item
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
        raise AssertionError("A roll must not happen without enough resource.")


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
        rng=SequenceRng(8, 1),
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


def test_encumbrance_penalty_reduces_ranged_attack_modifier(db_session):
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
    add_item(db_session, character.id, "Pedras Pesadas", quantity=1, base_weight=10_000.0)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.RANGED_ATTACK,
        action_key="overloaded-shot",
        rng=FixedRng(9),
    ).action

    # AGILITY 14 gives +2, the engaged-ranged penalty is -2, and OVERLOADED
    # carries the maximum agility penalty (-4).
    assert action.attack_modifier == -4
    assert action.attack_total == 5


def test_encumbrance_penalty_reduces_character_defense(db_session):
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
    ).value = 10
    add_item(db_session, character.id, "Pedras Pesadas", quantity=1, base_weight=10_000.0)
    hero.range_band = CombatRangeBand.ENGAGED.value
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))

    action = resolve_attack(
        db_session,
        encounter,
        bandit,
        hero,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="bandit-strike",
        rng=FixedRng(9),
    ).action

    # AGILITY 10 gives +0 defense; OVERLOADED subtracts the maximum penalty (-4).
    assert action.defense_modifier == -4
    assert action.defense_total == 6


def test_encumbrance_increases_stamina_cost_of_a_melee_attack(db_session):
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
    add_item(db_session, character.id, "Pedras Pesadas", quantity=1, base_weight=10_000.0)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="overloaded-melee",
        rng=FixedRng(1),
    ).action

    # Base melee cost is 2.0 stamina; OVERLOADED applies the 1.75x multiplier.
    assert action.resource_key == CharacterResourceKey.STAMINA.value
    assert action.resource_cost == 3.5


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
        rng=SequenceRng(13, 1),
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
    stored_bandit = db_session.get(NPC, bandit.actor_id)
    assert stored_bandit.hp_current == 9
    assert _character.stamina_current == 18
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


def test_hit_persists_damage_and_reduces_real_npc_hp(db_session):
    (
        _campaign,
        _region,
        _location,
        character,
        enemy,
        encounter,
        hero,
        bandit,
    ) = _setup(db_session)
    enemy.hp_current = enemy.hp_max = 20
    get_character_attribute(
        db_session,
        character.id,
        CharacterAttributeKey.STRENGTH,
    ).value = 14
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="damage-once",
        rng=SequenceRng(10, 4),
    ).action

    assert action.damage_roll == 4
    assert action.damage_dice == 1
    assert action.damage_modifier == 2
    assert action.damage_total == 6
    assert action.target_hp_before == 20
    assert action.target_hp_after == 14
    assert action.lethal is False
    assert enemy.hp_current == 14
    damage_event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_DAMAGE_APPLIED.value)
        .one()
    )
    assert json.loads(damage_event.payload_json)["damage_total"] == 6

    replay = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="damage-once",
        rng=SequenceRng(20, 6, 6),
    )
    assert replay.replayed is True
    assert enemy.hp_current == 14


def test_miss_persists_zero_damage_without_damage_event(db_session):
    (
        _campaign,
        _region,
        _location,
        _character,
        enemy,
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
        action_key="clean-miss",
        rng=FixedRng(2),
    ).action

    assert action.damage_total == 0
    assert action.target_hp_before == action.target_hp_after == 10
    assert enemy.hp_current == 10
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_DAMAGE_APPLIED.value)
        .count()
        == 0
    )


def test_critical_hit_rolls_two_damage_dice_and_modifier_once(db_session):
    (
        _campaign,
        _region,
        _location,
        character,
        enemy,
        encounter,
        hero,
        bandit,
    ) = _setup(db_session)
    enemy.hp_current = enemy.hp_max = 20
    get_character_attribute(
        db_session,
        character.id,
        CharacterAttributeKey.STRENGTH,
    ).value = 14
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="critical-damage",
        rng=SequenceRng(20, 2, 3),
    ).action

    assert action.outcome == CombatActionOutcome.CRITICAL_HIT.value
    assert action.damage_dice == 2
    assert action.damage_roll == 5
    assert action.damage_modifier == 2
    assert action.damage_total == 7
    assert enemy.hp_current == 13


def test_zero_hp_incapacitates_npc_and_ends_encounter_as_victory(db_session):
    (
        _campaign,
        _region,
        _location,
        _character,
        enemy,
        encounter,
        hero,
        bandit,
    ) = _setup(db_session)
    enemy.hp_current = 2
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="lethal-npc",
        rng=SequenceRng(10, 2),
    ).action

    assert action.lethal is False
    assert action.incapacitating is True
    assert enemy.hp_current == 0
    assert enemy.alive is True
    assert enemy.incapacitated is True
    assert bandit.active is False
    assert encounter.status == CombatEncounterStatus.VICTORY.value
    assert encounter.current_turn_order is None
    assert get_current_turn(db_session, encounter) is None
    assert action.turn.status == "COMPLETED"
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_PARTICIPANT_INCAPACITATED.value)
        .count()
        == 1
    )


def test_zero_hp_incapacitates_character_and_causes_defeat(db_session):
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
    character.hp_current = 1
    hero.range_band = CombatRangeBand.ENGAGED.value
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))

    action = resolve_attack(
        db_session,
        encounter,
        bandit,
        hero,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="lethal-character",
        rng=SequenceRng(10, 1),
    ).action

    assert action.lethal is False
    assert action.incapacitating is True
    assert character.hp_current == 0
    assert character.status == CharacterStatus.INCAPACITATED.value
    assert encounter.status == CombatEncounterStatus.DEFEAT.value
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_PARTICIPANT_INCAPACITATED.value)
        .count()
        == 1
    )


def test_zero_hp_incapacitates_simulated_player_persistently(
    db_session,
):
    campaign = create_campaign(db_session, "Simulated Player Combat")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    transported = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Rival",
        location_id=location.id,
        hp_current=1,
        hp_max=20,
    )
    db_session.add(transported)
    db_session.flush()
    encounter = start_encounter(
        db_session,
        campaign.id,
        location.id,
        (
            CombatantSpec(CombatActorType.CHARACTER, character.id, "heroes"),
            CombatantSpec(
                CombatActorType.SIMULATED_PLAYER,
                transported.id,
                "rivals",
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
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_attack(
        db_session,
        encounter,
        participants[character.id],
        participants[transported.id],
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="lethal-transported",
        rng=SequenceRng(10, 1),
    ).action

    assert action.lethal is False
    assert action.incapacitating is True
    assert transported.hp_current == 0
    assert transported.status == SimulatedPlayerStatus.INCAPACITATED.value
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_PARTICIPANT_INCAPACITATED.value)
        .count()
        == 1
    )


def test_melee_attack_spends_stamina_once_and_persists_snapshot(db_session):
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
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    first = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="stamina-once",
        rng=FixedRng(2),
    )

    assert first.action.resource_key == CharacterResourceKey.STAMINA.value
    assert first.action.resource_cost == 2
    assert first.action.resource_before == 20
    assert first.action.resource_after == 18
    assert character.stamina_current == 18
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_RESOURCE_SPENT.value)
        .count()
        == 1
    )

    replay = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="stamina-once",
        rng=ExplodingRng(),
    )
    assert replay.replayed is True
    assert character.stamina_current == 18
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_RESOURCE_SPENT.value)
        .count()
        == 1
    )


def test_ranged_attack_spends_one_stamina_even_when_it_misses(db_session):
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
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_attack(
        db_session,
        encounter,
        hero,
        bandit,
        action_type=CombatActionType.RANGED_ATTACK,
        action_key="miss-costs-stamina",
        rng=FixedRng(1),
    ).action

    assert action.outcome == CombatActionOutcome.CRITICAL_MISS.value
    assert action.resource_cost == 1
    assert character.stamina_current == 19


def test_insufficient_stamina_rejects_before_roll_and_keeps_turn(db_session):
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
    character.stamina_current = 1
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    current = get_current_turn(db_session, encounter)

    with pytest.raises(CombatResourceError, match="Insufficient stamina"):
        resolve_attack(
            db_session,
            encounter,
            hero,
            bandit,
            action_type=CombatActionType.MELEE_ATTACK,
            action_key="too-tired",
            rng=ExplodingRng(),
        )

    assert character.stamina_current == 1
    assert db_session.query(CombatAction).count() == 0
    assert get_current_turn(db_session, encounter).id == current.id
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_RESOURCE_SPENT.value)
        .count()
        == 0
    )


def test_npc_attack_uses_npcs_own_persistent_stamina(db_session):
    (
        _campaign,
        _region,
        _location,
        _character,
        enemy,
        encounter,
        hero,
        bandit,
    ) = _setup(db_session)
    hero.range_band = CombatRangeBand.ENGAGED.value
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))

    action = resolve_attack(
        db_session,
        encounter,
        bandit,
        hero,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="npc-stamina",
        rng=FixedRng(1),
    ).action

    assert action.resource_before == 10
    assert action.resource_after == 8
    assert enemy.stamina_current == 8
