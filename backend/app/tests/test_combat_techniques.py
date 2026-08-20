import pytest

from app.core.enums import (
    CharacterAttributeKey,
    CharacterResourceKey,
    CombatActionOutcome,
    CombatActionType,
    CombatActorType,
    CombatConditionType,
    CombatDamageType,
    CombatRangeBand,
)
from app.db.models.combat import CombatAction, CombatCondition, CombatParticipant
from app.db.models.domain import DomainDefinition
from app.db.models.npc import NPC
from app.db.models.skill import CombatTechniqueProfile, TechniqueUseRecord
from app.game.character.service import create_character
from app.game.combat.encounters import CombatantSpec, start_encounter
from app.game.combat.defense import configure_actor_combat_defense
from app.game.combat.techniques import (
    CombatTechniqueError,
    configure_combat_technique,
    resolve_combat_technique,
)
from app.game.combat.turns import get_current_turn, roll_initiative
from app.game.skills.techniques import create_technique, grant_technique
from app.game.world.seed import create_campaign, seed_initial_region


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


class ExplodingRng:
    def randint(self, _minimum: int, _maximum: int) -> int:
        raise AssertionError("A replayed or rejected technique must not roll dice.")


def _setup(
    db_session,
    *,
    grant: bool = True,
    damage_type: CombatDamageType = CombatDamageType.PHYSICAL,
):
    for key, family in (("SWORD", "WEAPON"), ("WIND", "MANIFESTATION")):
        if db_session.get(DomainDefinition, key) is None:
            db_session.add(DomainDefinition(key=key, family=family, description=""))
    campaign = create_campaign(db_session, "Combat Technique")
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
        name="Guardião",
        role="guardian",
        hp_current=40,
        hp_max=40,
    )
    db_session.add(enemy)
    technique = create_technique(
        db_session,
        skill_name="Esgrima Arcana",
        name="Corte de Vento",
        description="Uma lâmina de vento concentrado.",
        domain_keys=("SWORD", "WIND"),
    )
    if grant:
        grant_technique(db_session, campaign.id, character, technique)
    profile = configure_combat_technique(
        db_session,
        technique,
        action_type=CombatActionType.RANGED_ATTACK,
        attack_attribute=CharacterAttributeKey.INTELLIGENCE,
        resource_key=CharacterResourceKey.MANA,
        resource_cost=3,
        base_damage_dice=2,
        damage_die_sides=8,
        damage_attribute=CharacterAttributeKey.INTELLIGENCE,
        damage_type=damage_type,
        condition_type=CombatConditionType.STUNNED,
        condition_duration_turns=1,
    )
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
                "guardians",
                range_band=CombatRangeBand.FAR,
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
        technique,
        profile,
        encounter,
        participants[character.id],
        participants[enemy.id],
    )


def test_known_combat_technique_uses_profile_cost_damage_condition_and_evidence(
    db_session,
):
    (
        _campaign,
        character,
        enemy,
        technique,
        _profile,
        encounter,
        hero,
        guardian,
    ) = _setup(db_session)
    intelligence = next(row for row in character.attributes if row.key == "INTELLIGENCE")
    intelligence.value = 14
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    result = resolve_combat_technique(
        db_session,
        encounter,
        hero,
        guardian,
        technique_id=technique.id,
        action_key="combat-technique-1",
        rng=SequenceRng(10, 4, 5),
    )

    assert result.replayed is False
    assert result.action.technique_id == technique.id
    assert result.action.attack_attribute == CharacterAttributeKey.INTELLIGENCE.value
    assert result.action.attack_modifier == 2
    assert result.action.resource_key == CharacterResourceKey.MANA.value
    assert result.action.resource_cost == 3
    assert character.mana_current == 7
    assert result.action.base_damage_dice == 2
    assert result.action.damage_die_sides == 8
    assert result.action.damage_dice == 2
    assert result.action.damage_roll == 9
    assert result.action.damage_modifier == 2
    assert result.action.damage_type == CombatDamageType.PHYSICAL.value
    assert result.action.damage_total == 11
    assert enemy.hp_current == 29
    assert result.condition is not None
    assert result.condition.condition_type == CombatConditionType.STUNNED.value
    assert result.condition.source_action_id == result.action.id
    assert {gain.domain_key for gain in result.progression_outcome.domains} == {
        "SWORD",
        "WIND",
    }
    assert len(result.progression_outcome.synergies) == 1
    record = db_session.query(TechniqueUseRecord).one()
    assert record.roll == result.action.attack_roll
    assert record.dc == result.action.defense_total
    assert record.success is True

    current = get_current_turn(db_session, encounter)
    assert current.participant_id == hero.id
    assert result.condition.active is False


def test_combat_technique_uses_configured_damage_type_and_resistance(db_session):
    (
        _campaign,
        _character,
        enemy,
        technique,
        profile,
        encounter,
        hero,
        guardian,
    ) = _setup(db_session, damage_type=CombatDamageType.FIRE)
    configure_actor_combat_defense(
        db_session,
        CombatActorType.NPC,
        enemy.id,
        armor_rating=10,
        resistances={CombatDamageType.FIRE: 3},
    )
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    result = resolve_combat_technique(
        db_session,
        encounter,
        hero,
        guardian,
        technique_id=technique.id,
        action_key="fire-technique",
        rng=SequenceRng(10, 4, 5),
    )

    assert profile.damage_type == CombatDamageType.FIRE.value
    assert result.action.damage_type == CombatDamageType.FIRE.value
    assert result.action.damage_before_mitigation == 9
    assert result.action.armor_mitigation == 0
    assert result.action.resistance_mitigation == 3
    assert result.action.damage_total == 6


def test_combat_technique_retry_does_not_repeat_cost_damage_or_condition(db_session):
    (
        _campaign,
        character,
        enemy,
        technique,
        _profile,
        encounter,
        hero,
        guardian,
    ) = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    first = resolve_combat_technique(
        db_session,
        encounter,
        hero,
        guardian,
        technique_id=technique.id,
        action_key="stable-technique",
        rng=SequenceRng(10, 2, 2),
    )
    mana_after = character.mana_current
    hp_after = enemy.hp_current

    replay = resolve_combat_technique(
        db_session,
        encounter,
        hero,
        guardian,
        technique_id=technique.id,
        action_key="stable-technique",
        rng=ExplodingRng(),
    )

    assert replay.replayed is True
    assert replay.action.id == first.action.id
    assert character.mana_current == mana_after == 7
    assert enemy.hp_current == hp_after
    assert db_session.query(CombatAction).count() == 1
    assert db_session.query(TechniqueUseRecord).count() == 1
    assert db_session.query(CombatCondition).count() == 1


def test_unlearned_or_unconfigured_technique_cannot_be_used(db_session):
    (
        _campaign,
        character,
        _enemy,
        technique,
        _profile,
        encounter,
        hero,
        guardian,
    ) = _setup(db_session, grant=False)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    with pytest.raises(CombatTechniqueError, match="does not know"):
        resolve_combat_technique(
            db_session,
            encounter,
            hero,
            guardian,
            technique_id=technique.id,
            action_key="stolen-technique",
            rng=ExplodingRng(),
        )
    unconfigured = create_technique(
        db_session,
        skill_name="Esgrima Arcana",
        name="Corte Incompleto",
        domain_keys=("SWORD",),
    )
    grant_technique(db_session, encounter.campaign_id, character, unconfigured)
    with pytest.raises(CombatTechniqueError, match="no authoritative"):
        resolve_combat_technique(
            db_session,
            encounter,
            hero,
            guardian,
            technique_id=unconfigured.id,
            action_key="unconfigured-technique",
            rng=ExplodingRng(),
        )
    assert db_session.query(CombatAction).count() == 0


def test_profile_is_immutable_and_rejects_luck_or_partial_condition(db_session):
    (
        _campaign,
        _character,
        _enemy,
        technique,
        profile,
        _encounter,
        _hero,
        _guardian,
    ) = _setup(db_session)
    same = configure_combat_technique(
        db_session,
        technique,
        action_type=CombatActionType.RANGED_ATTACK,
        attack_attribute=CharacterAttributeKey.INTELLIGENCE,
        resource_key=CharacterResourceKey.MANA,
        resource_cost=3,
        base_damage_dice=2,
        damage_die_sides=8,
        damage_attribute=CharacterAttributeKey.INTELLIGENCE,
        condition_type=CombatConditionType.STUNNED,
        condition_duration_turns=1,
    )
    assert same is profile
    with pytest.raises(CombatTechniqueError, match="different mechanics"):
        configure_combat_technique(
            db_session,
            technique,
            action_type=CombatActionType.RANGED_ATTACK,
            attack_attribute=CharacterAttributeKey.INTELLIGENCE,
            resource_key=CharacterResourceKey.MANA,
            resource_cost=4,
            base_damage_dice=2,
            damage_die_sides=8,
            damage_attribute=CharacterAttributeKey.INTELLIGENCE,
            condition_type=CombatConditionType.STUNNED,
            condition_duration_turns=1,
        )

    invalid = create_technique(
        db_session,
        skill_name="Esgrima Arcana",
        name="Golpe da Fortuna",
        domain_keys=("SWORD",),
    )
    with pytest.raises(CombatTechniqueError, match="Luck cannot"):
        configure_combat_technique(
            db_session,
            invalid,
            action_type=CombatActionType.MELEE_ATTACK,
            attack_attribute=CharacterAttributeKey.LUCK,
            resource_key=CharacterResourceKey.STAMINA,
            resource_cost=1,
            base_damage_dice=1,
            damage_die_sides=6,
            damage_attribute=CharacterAttributeKey.STRENGTH,
        )
    with pytest.raises(CombatTechniqueError, match="configured together"):
        configure_combat_technique(
            db_session,
            invalid,
            action_type=CombatActionType.MELEE_ATTACK,
            attack_attribute=CharacterAttributeKey.STRENGTH,
            resource_key=CharacterResourceKey.STAMINA,
            resource_cost=1,
            base_damage_dice=1,
            damage_die_sides=6,
            damage_attribute=CharacterAttributeKey.STRENGTH,
            condition_type=CombatConditionType.EXPOSED,
        )

    assert db_session.query(CombatTechniqueProfile).count() == 1


def test_insufficient_mana_rejects_technique_before_roll(db_session):
    (
        _campaign,
        character,
        _enemy,
        technique,
        _profile,
        encounter,
        hero,
        guardian,
    ) = _setup(db_session)
    character.mana_current = 2
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    current = get_current_turn(db_session, encounter)

    with pytest.raises(ValueError, match="Insufficient mana"):
        resolve_combat_technique(
            db_session,
            encounter,
            hero,
            guardian,
            technique_id=technique.id,
            action_key="no-mana",
            rng=ExplodingRng(),
        )

    assert character.mana_current == 2
    assert db_session.query(CombatAction).count() == 0
    assert get_current_turn(db_session, encounter).id == current.id


def test_missed_technique_spends_resource_but_does_not_apply_condition(db_session):
    (
        _campaign,
        character,
        enemy,
        technique,
        _profile,
        encounter,
        hero,
        guardian,
    ) = _setup(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    result = resolve_combat_technique(
        db_session,
        encounter,
        hero,
        guardian,
        technique_id=technique.id,
        action_key="missed-technique",
        rng=SequenceRng(1),
    )

    assert result.action.outcome == CombatActionOutcome.CRITICAL_MISS.value
    assert result.action.damage_total == 0
    assert result.condition is None
    assert character.mana_current == 7
    assert enemy.hp_current == 40
    assert result.progression_outcome.domains == ()
