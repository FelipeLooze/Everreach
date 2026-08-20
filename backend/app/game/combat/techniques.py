import random
from dataclasses import dataclass
from math import isfinite

from sqlalchemy.orm import Session

from app.core.enums import (
    BodyArea,
    CharacterAttributeKey,
    CharacterResourceKey,
    CombatActionOutcome,
    CombatActionType,
    CombatActorType,
    CombatConditionType,
    CombatDamageType,
    PhysicalDamageProfile,
)
from app.db.models.character import Character
from app.db.models.combat import CombatAction, CombatCondition, CombatEncounter, CombatParticipant
from app.db.models.skill import (
    CharacterTechnique,
    CombatTechniqueProfile,
    Technique,
    TechniqueUseRecord,
)
from app.game.combat.actions import (
    AttackMechanics,
    CombatActionResolution,
    resolve_profiled_attack,
)
from app.game.combat.conditions import apply_condition
from app.game.progression.outcomes import ProgressionOutcome
from app.game.skills.techniques import technique_progression_outcome


class CombatTechniqueError(ValueError):
    pass


@dataclass(frozen=True)
class CombatTechniqueResolution:
    technique: Technique
    profile: CombatTechniqueProfile
    action: CombatAction
    condition: CombatCondition | None
    progression_outcome: ProgressionOutcome
    replayed: bool


def configure_combat_technique(
    db: Session,
    technique: Technique,
    *,
    action_type: CombatActionType,
    attack_attribute: CharacterAttributeKey,
    resource_key: CharacterResourceKey,
    resource_cost: float,
    base_damage_dice: int,
    damage_die_sides: int,
    damage_attribute: CharacterAttributeKey,
    condition_type: CombatConditionType | None = None,
    condition_duration_turns: int | None = None,
    damage_type: CombatDamageType = CombatDamageType.PHYSICAL,
) -> CombatTechniqueProfile:
    """Attach immutable, structured combat mechanics to a discovered technique."""
    if db.get(Technique, technique.id) is None:
        raise CombatTechniqueError("Technique must be persisted before configuration.")
    if not isinstance(action_type, CombatActionType):
        raise CombatTechniqueError("Invalid technique attack type.")
    if not isinstance(attack_attribute, CharacterAttributeKey):
        raise CombatTechniqueError("Invalid technique attack attribute.")
    if not isinstance(damage_attribute, CharacterAttributeKey):
        raise CombatTechniqueError("Invalid technique damage attribute.")
    if CharacterAttributeKey.LUCK in {attack_attribute, damage_attribute}:
        raise CombatTechniqueError("Luck cannot resolve technique attacks or damage.")
    if not isinstance(damage_type, CombatDamageType):
        raise CombatTechniqueError("Invalid technique damage type.")
    if resource_key not in {
        CharacterResourceKey.MANA,
        CharacterResourceKey.STAMINA,
    }:
        raise CombatTechniqueError("Combat technique must spend mana or stamina.")
    if not isfinite(resource_cost) or resource_cost <= 0:
        raise CombatTechniqueError("Technique resource cost must be finite and positive.")
    if not 1 <= base_damage_dice <= 5:
        raise CombatTechniqueError("Technique must roll between one and five damage dice.")
    if not 2 <= damage_die_sides <= 100:
        raise CombatTechniqueError("Technique damage die must have between 2 and 100 sides.")
    if (condition_type is None) != (condition_duration_turns is None):
        raise CombatTechniqueError("Technique condition and duration must be configured together.")
    if condition_type is not None:
        if not isinstance(condition_type, CombatConditionType):
            raise CombatTechniqueError("Invalid technique condition type.")
        if not 1 <= condition_duration_turns <= 10:
            raise CombatTechniqueError("Technique condition must last between 1 and 10 turns.")

    values = {
        "action_type": action_type.value,
        "attack_attribute": attack_attribute.value,
        "resource_key": resource_key.value,
        "resource_cost": resource_cost,
        "base_damage_dice": base_damage_dice,
        "damage_die_sides": damage_die_sides,
        "damage_attribute": damage_attribute.value,
        "damage_type": damage_type.value,
        "condition_type": condition_type.value if condition_type else None,
        "condition_duration_turns": condition_duration_turns,
    }
    existing = db.get(CombatTechniqueProfile, technique.id)
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in values.items()):
            raise CombatTechniqueError("Combat technique already has different mechanics.")
        return existing
    profile = CombatTechniqueProfile(technique_id=technique.id, **values)
    db.add(profile)
    db.flush()
    return profile


def resolve_combat_technique(
    db: Session,
    encounter: CombatEncounter,
    actor: CombatParticipant,
    target: CombatParticipant,
    *,
    technique_id: str,
    action_key: str,
    rng: random.Random | None = None,
) -> CombatTechniqueResolution:
    if actor.actor_type != CombatActorType.CHARACTER.value:
        raise CombatTechniqueError("Only characters can use discovered techniques.")
    character = db.get(Character, actor.actor_id)
    if character is None or character.campaign_id != encounter.campaign_id:
        raise CombatTechniqueError("Technique user does not belong to encounter campaign.")
    technique = db.get(Technique, technique_id)
    if technique is None:
        raise CombatTechniqueError("Unknown technique.")
    ownership = (
        db.query(CharacterTechnique)
        .filter(
            CharacterTechnique.character_id == character.id,
            CharacterTechnique.technique_id == technique.id,
        )
        .one_or_none()
    )
    if ownership is None:
        raise CombatTechniqueError("Character does not know this technique.")
    profile = db.get(CombatTechniqueProfile, technique.id)
    if profile is None:
        raise CombatTechniqueError("Technique has no authoritative combat mechanics.")

    normalized_key = action_key.strip().lower()
    mechanics = AttackMechanics(
        action_type=CombatActionType(profile.action_type),
        attack_attribute=CharacterAttributeKey(profile.attack_attribute),
        resource_key=CharacterResourceKey(profile.resource_key),
        resource_cost=profile.resource_cost,
        base_damage_dice=profile.base_damage_dice,
        damage_die_sides=profile.damage_die_sides,
        damage_attribute=CharacterAttributeKey(profile.damage_attribute),
        damage_type=CombatDamageType(profile.damage_type),
        technique_id=technique.id,
        physical_damage_profile=(
            PhysicalDamageProfile.BLUNT
            if profile.damage_type == CombatDamageType.PHYSICAL.value
            else None
        ),
        target_body_area=(
            BodyArea.TORSO
            if profile.damage_type == CombatDamageType.PHYSICAL.value
            else None
        ),
    )
    attack: CombatActionResolution = resolve_profiled_attack(
        db,
        encounter,
        actor,
        target,
        mechanics=mechanics,
        action_key=normalized_key,
        rng=rng,
    )
    record = _get_or_create_use_record(
        db,
        encounter,
        character,
        technique,
        attack.action,
    )
    condition = _apply_profile_condition(
        db,
        encounter,
        target,
        profile,
        attack.action,
    )
    return CombatTechniqueResolution(
        technique=technique,
        profile=profile,
        action=attack.action,
        condition=condition,
        progression_outcome=technique_progression_outcome(
            character,
            technique,
            tuple(row.domain_key for row in technique.domains),
            record,
        ),
        replayed=attack.replayed,
    )


def _get_or_create_use_record(
    db: Session,
    encounter: CombatEncounter,
    character: Character,
    technique: Technique,
    action: CombatAction,
) -> TechniqueUseRecord:
    existing = (
        db.query(TechniqueUseRecord)
        .filter(
            TechniqueUseRecord.campaign_id == encounter.campaign_id,
            TechniqueUseRecord.character_id == character.id,
            TechniqueUseRecord.action_key == action.action_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.technique_id != technique.id:
            raise CombatTechniqueError("Action key belongs to another technique use.")
        return existing
    record = TechniqueUseRecord(
        campaign_id=encounter.campaign_id,
        character_id=character.id,
        technique_id=technique.id,
        action_key=action.action_key,
        roll=action.attack_roll,
        modifier=action.attack_modifier,
        total=action.attack_total,
        dc=action.defense_total,
        success=action.outcome
        in {CombatActionOutcome.HIT.value, CombatActionOutcome.CRITICAL_HIT.value},
        critical=action.outcome == CombatActionOutcome.CRITICAL_HIT.value,
        world_minute=action.created_world_minute,
    )
    db.add(record)
    db.flush()
    return record


def _apply_profile_condition(
    db: Session,
    encounter: CombatEncounter,
    target: CombatParticipant,
    profile: CombatTechniqueProfile,
    action: CombatAction,
) -> CombatCondition | None:
    if (
        profile.condition_type is None
        or action.outcome
        not in {CombatActionOutcome.HIT.value, CombatActionOutcome.CRITICAL_HIT.value}
        or not target.active
    ):
        return None
    return apply_condition(
        db,
        encounter,
        target,
        condition_type=CombatConditionType(profile.condition_type),
        duration_turns=profile.condition_duration_turns,
        application_key=f"action:{action.id}",
        source_action=action,
    ).condition
