"""Losing a fight: the character faints and wakes up back in the village.

The user's rule (2026-10-24), for now: no permadeath. Before this an
incapacitated character could not act at all ("precisa ser estabilizado")
and nothing ever stabilized them, so one lost fight ended the save.
"""

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterStatus,
    CombatActorType,
    CombatEncounterStatus,
    CombatIncapacitationStatus,
    DiscoveryStatus,
)
from app.db.models.combat import CombatIncapacitation
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.game.combat.encounters import end_encounter, get_active_encounter_for_actor
from app.game.discovery.service import set_location_discovery
from app.game.time import clock

HOURS_OUT = 4
HP_ON_WAKING = 0.25


def _where_to_wake(db: Session, character) -> Location | None:
    """The inn of the village people live in; its square if it has none."""
    village_id = (
        db.query(NPC.location_id)
        .filter(NPC.campaign_id == character.campaign_id, NPC.routine_json != "[]")
        .first()
    )
    if village_id is None:
        return None
    inn = (
        db.query(Location)
        .filter(Location.parent_location_id == village_id[0], Location.type == "inn")
        .first()
    )
    return inn or db.get(Location, village_id[0])


def faint_and_wake(db: Session, campaign_id: str, character) -> str | None:
    """None unless the character is down; otherwise wake them and say how."""
    if character.status != CharacterStatus.INCAPACITATED.value:
        return None
    encounter = get_active_encounter_for_actor(db, CombatActorType.CHARACTER, character.id)
    if encounter is not None:
        end_encounter(db, encounter, CombatEncounterStatus.DEFEAT, reason="character_fainted")
    for incapacitation in db.query(CombatIncapacitation).filter(
        CombatIncapacitation.actor_type == CombatActorType.CHARACTER.value,
        CombatIncapacitation.actor_id == character.id,
        CombatIncapacitation.status.in_(
            (CombatIncapacitationStatus.CRITICAL.value, CombatIncapacitationStatus.STABILIZED.value)
        ),
    ):
        incapacitation.status = CombatIncapacitationStatus.RECOVERED.value
        incapacitation.resolution_reason = "fainted_and_carried_home"
    character.status = CharacterStatus.ALIVE.value
    character.hp_current = max(1.0, round(float(character.hp_max) * HP_ON_WAKING, 1))
    fell_at = db.get(Location, character.location_id)
    wake = _where_to_wake(db, character)
    if wake is not None:
        character.location_id = wake.id
        set_location_discovery(db, character.id, wake.id, DiscoveryStatus.VISITED)
    clock.advance_world_time(db, campaign_id, HOURS_OUT * 60)
    db.flush()
    where = wake.name if wake is not None else "um lugar seguro"
    fell = f" em {fell_at.name}" if fell_at is not None else ""
    return (
        f"{character.name} desmaia{fell}. Horas depois, acorda em {where}, ferido "
        f"({character.hp_current:g}/{character.hp_max:g} de vida): alguém o encontrou e o trouxe de volta."
    )
