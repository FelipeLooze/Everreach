import random
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterAttributeKey,
    CombatActionOutcome,
    CombatActionType,
    CombatActorType,
    EventType,
)
from app.db.models.character import Character
from app.db.models.combat import CombatAction, CombatEncounter, CombatParticipant
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.game.attributes.service import attribute_check_modifier, get_character_attribute
from app.game.character.service import kill_character
from app.game.combat.encounters import list_active_participants, remove_participant
from app.game.dice import roll
from app.game.players.death import kill_simulated_player
from app.services.event_log import log_event


@dataclass(frozen=True)
class DamageResolution:
    damage_total: int
    target_hp_before: float
    target_hp_after: float
    lethal: bool
    encounter_should_end: bool


class CombatDamageError(ValueError):
    pass


def apply_attack_damage(
    db: Session,
    encounter: CombatEncounter,
    action: CombatAction,
    actor: CombatParticipant,
    target: CombatParticipant,
    *,
    rng: random.Random | None = None,
) -> DamageResolution:
    """Apply the damage of a persisted hit exactly once to the target's real HP."""
    if action.encounter_id != encounter.id:
        raise CombatDamageError("Combat action does not belong to encounter.")
    if (
        action.actor_participant_id != actor.id
        or action.target_participant_id != target.id
    ):
        raise CombatDamageError("Damage participants do not match combat action.")
    if action.damage_total is not None:
        return DamageResolution(
            damage_total=action.damage_total,
            target_hp_before=float(action.target_hp_before or 0),
            target_hp_after=float(action.target_hp_after or 0),
            lethal=bool(action.lethal),
            encounter_should_end=_has_one_or_fewer_active_sides(db, encounter.id),
        )

    target_actor = _target_actor(db, target)
    hp_before = max(0.0, float(target_actor.hp_current))
    if action.outcome in {
        CombatActionOutcome.MISS.value,
        CombatActionOutcome.CRITICAL_MISS.value,
    }:
        action.damage_roll = 0
        action.damage_dice = 0
        action.damage_modifier = 0
        action.damage_total = 0
        action.target_hp_before = hp_before
        action.target_hp_after = hp_before
        action.lethal = False
        db.flush()
        return DamageResolution(0, hp_before, hp_before, False, False)

    base_dice = action.base_damage_dice or 1
    die_sides = action.damage_die_sides or 6
    dice_count = base_dice * (
        2 if action.outcome == CombatActionOutcome.CRITICAL_HIT.value else 1
    )
    damage_roll = sum(roll(die_sides, rng=rng).raw for _ in range(dice_count))
    damage_attribute = (
        CharacterAttributeKey(action.damage_attribute)
        if action.damage_attribute
        else (
            CharacterAttributeKey.STRENGTH
            if action.action_type == CombatActionType.MELEE_ATTACK.value
            else CharacterAttributeKey.AGILITY
        )
    )
    damage_modifier = _damage_modifier(db, actor, damage_attribute)
    damage_total = max(1, damage_roll + damage_modifier)
    hp_after = max(0.0, hp_before - damage_total)
    lethal = hp_before > 0 and hp_after <= 0
    target_actor.hp_current = hp_after
    action.damage_roll = damage_roll
    action.damage_dice = dice_count
    action.damage_modifier = damage_modifier
    action.damage_total = damage_total
    action.target_hp_before = hp_before
    action.target_hp_after = hp_after
    action.lethal = lethal
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_DAMAGE_APPLIED,
        actor_type=actor.actor_type.lower(),
        actor_id=actor.actor_id,
        payload={
            "encounter_id": encounter.id,
            "action_id": action.id,
            "actor_participant_id": actor.id,
            "target_participant_id": target.id,
            "damage_roll": damage_roll,
            "damage_dice": dice_count,
            "damage_die_sides": die_sides,
            "damage_modifier": damage_modifier,
            "damage_total": damage_total,
            "target_hp_before": hp_before,
            "target_hp_after": hp_after,
            "lethal": lethal,
        },
    )
    if lethal:
        cause = f"combat_action:{action.id}"
        _kill_target(db, encounter, target, target_actor, cause)
        remove_participant(db, encounter, target, reason=cause)
    db.flush()
    return DamageResolution(
        damage_total,
        hp_before,
        hp_after,
        lethal,
        _has_one_or_fewer_active_sides(db, encounter.id),
    )


def _target_actor(
    db: Session,
    participant: CombatParticipant,
) -> Character | NPC | SimulatedPlayer:
    model = {
        CombatActorType.CHARACTER.value: Character,
        CombatActorType.NPC.value: NPC,
        CombatActorType.SIMULATED_PLAYER.value: SimulatedPlayer,
    }.get(participant.actor_type)
    actor = db.get(model, participant.actor_id) if model is not None else None
    if actor is None:
        raise CombatDamageError("Combat damage target does not exist.")
    return actor


def _damage_modifier(
    db: Session,
    participant: CombatParticipant,
    attribute_key: CharacterAttributeKey,
) -> int:
    if participant.actor_type != CombatActorType.CHARACTER.value:
        return 0
    attribute = get_character_attribute(db, participant.actor_id, attribute_key)
    return attribute_check_modifier(attribute.value)


def _kill_target(
    db: Session,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    actor: Character | NPC | SimulatedPlayer,
    cause: str,
) -> None:
    if participant.actor_type == CombatActorType.CHARACTER.value:
        kill_character(db, encounter.campaign_id, actor, cause=cause)
    elif participant.actor_type == CombatActorType.NPC.value:
        actor.alive = False
        log_event(
            db,
            encounter.campaign_id,
            EventType.NPC_DIED,
            actor_type="npc",
            actor_id=actor.id,
            payload={"npc_id": actor.id, "name": actor.name, "cause": cause},
            importance=5,
        )
    else:
        kill_simulated_player(
            db,
            encounter.campaign_id,
            actor,
            cause=cause,
        )


def _has_one_or_fewer_active_sides(db: Session, encounter_id: str) -> bool:
    return len(
        {row.side_key for row in list_active_participants(db, encounter_id)}
    ) <= 1
