from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType
from app.db.models.character import Character
from app.db.models.combat import CombatParticipant
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.game.combat.encounters import (
    get_active_encounter_for_actor,
    list_active_participants,
)
from app.game.combat.turns import get_current_turn


@dataclass(frozen=True)
class CombatParticipantSnapshot:
    participant_id: str
    actor_type: str
    actor_id: str
    name: str
    side_key: str
    range_band: str
    hp_current: float
    hp_max: float
    is_current_turn: bool


@dataclass(frozen=True)
class CombatEncounterSnapshot:
    encounter_id: str
    status: str
    round_number: int
    participants: tuple[CombatParticipantSnapshot, ...]


def build_active_encounter_snapshot(
    db: Session,
    character_id: str,
) -> CombatEncounterSnapshot | None:
    """Read-only view of the character's active fight, if any, for GameState."""
    encounter = get_active_encounter_for_actor(
        db, CombatActorType.CHARACTER, character_id
    )
    if encounter is None:
        return None

    current_turn = get_current_turn(db, encounter)
    current_participant_id = current_turn.participant_id if current_turn else None

    participants = tuple(
        _participant_snapshot(db, participant, current_participant_id)
        for participant in list_active_participants(db, encounter.id)
    )

    return CombatEncounterSnapshot(
        encounter_id=encounter.id,
        status=encounter.status,
        round_number=encounter.round_number,
        participants=participants,
    )


def _participant_snapshot(
    db: Session,
    participant: CombatParticipant,
    current_participant_id: str | None,
) -> CombatParticipantSnapshot:
    actor = _actor(db, participant)
    return CombatParticipantSnapshot(
        participant_id=participant.id,
        actor_type=participant.actor_type,
        actor_id=participant.actor_id,
        name=actor.name if actor is not None else "desconhecido",
        side_key=participant.side_key,
        range_band=participant.range_band,
        hp_current=float(actor.hp_current) if actor is not None else 0.0,
        hp_max=float(actor.hp_max) if actor is not None else 0.0,
        is_current_turn=participant.id == current_participant_id,
    )


def _actor(
    db: Session,
    participant: CombatParticipant,
) -> Character | NPC | SimulatedPlayer | None:
    model = {
        CombatActorType.CHARACTER.value: Character,
        CombatActorType.NPC.value: NPC,
        CombatActorType.SIMULATED_PLAYER.value: SimulatedPlayer,
    }.get(participant.actor_type)
    return db.get(model, participant.actor_id) if model is not None else None
