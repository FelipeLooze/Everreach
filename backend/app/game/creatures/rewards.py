"""Authoritative progression rewards for creature defeats."""

from sqlalchemy.orm import Session

from app.ai.llm_service import LLMService
from app.core.enums import CharacterXPSource, CombatActorType
from app.db.models.character import Character
from app.db.models.combat import CombatAction, CombatParticipant
from app.db.models.npc import NPC
from app.game.creatures.species import get as get_species
from app.game.progression.outcomes import (
    CharacterXPGain,
    ProgressionOutcome,
    resolve_progression_outcome,
)


def grant_new_creature_defeat_rewards(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    character: Character,
    dead_before: set[str],
) -> list[tuple[NPC, float]]:
    """Grant dataset XP once for creatures actually killed by this character."""
    dead_now = db.query(NPC).filter(
        NPC.campaign_id == campaign_id,
        NPC.creature_species.is_not(None),
        NPC.alive.is_(False),
    ).all()
    rewarded: list[tuple[NPC, float]] = []
    for creature in dead_now:
        if creature.id in dead_before or not _character_dealt_finishing_blow(
            db, creature.id, character.id
        ):
            continue
        species = get_species(creature.creature_species)
        if species is None or species.xp <= 0:
            continue
        profile = _profile(creature)
        level = int(profile.get("level", species.level))
        took_damage = _character_took_damage_in_encounter(
            db, creature.id, character.id
        )
        if not took_damage and level < 1:
            continue
        resolution = resolve_progression_outcome(
            db,
            llm_service,
            campaign_id,
            character,
            ProgressionOutcome(
                outcome_key=f"creature-defeat:{creature.id}",
                character_xp=CharacterXPGain(
                    amount=float(species.xp),
                    source=CharacterXPSource.DANGER_OVERCOME,
                ),
            ),
        )
        if resolution.applied:
            rewarded.append((creature, float(species.xp)))
    return rewarded


def _profile(creature: NPC) -> dict:
    import json

    return json.loads(creature.profile_json or "{}")


def _creature_participants(db: Session, creature_id: str) -> list[CombatParticipant]:
    return db.query(CombatParticipant).filter(
        CombatParticipant.actor_type == CombatActorType.NPC.value,
        CombatParticipant.actor_id == creature_id,
    ).all()


def _character_dealt_finishing_blow(
    db: Session,
    creature_id: str,
    character_id: str,
) -> bool:
    for target in _creature_participants(db, creature_id):
        actions = db.query(CombatAction).filter(
            CombatAction.target_participant_id == target.id,
            CombatAction.target_hp_after <= 0,
        ).all()
        for action in actions:
            actor = db.get(CombatParticipant, action.actor_participant_id)
            if (
                actor is not None
                and actor.actor_type == CombatActorType.CHARACTER.value
                and actor.actor_id == character_id
            ):
                return True
    return False


def _character_took_damage_in_encounter(
    db: Session,
    creature_id: str,
    character_id: str,
) -> bool:
    encounter_ids = {
        participant.encounter_id
        for participant in _creature_participants(db, creature_id)
    }
    if not encounter_ids:
        return False
    character_participants = db.query(CombatParticipant).filter(
        CombatParticipant.encounter_id.in_(encounter_ids),
        CombatParticipant.actor_type == CombatActorType.CHARACTER.value,
        CombatParticipant.actor_id == character_id,
    ).all()
    ids = [participant.id for participant in character_participants]
    if not ids:
        return False
    return db.query(CombatAction).filter(
        CombatAction.target_participant_id.in_(ids),
        CombatAction.damage_total > 0,
    ).first() is not None
