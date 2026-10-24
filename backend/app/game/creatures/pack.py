"""Animals that live in groups fight as one: attack a wolf, or be ambushed by
one, and the rest of its pack that is awake at the place comes too (the
dataset's "matilhas de 3 a 6"). A lone wolf was trivially easy."""

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, NPCActivity
from app.db.models.npc import NPC
from app.game.combat.encounters import get_active_encounter_for_actor

MAX_PACK = 4  # the one attacked or attacking included


def pack_of(db: Session, creature: NPC) -> list[NPC]:
    """The others of the same species awake at the same place, free to join."""
    if creature.creature_species is None:
        return []
    others = (
        db.query(NPC)
        .filter(
            NPC.location_id == creature.location_id,
            NPC.creature_species == creature.creature_species,
            NPC.id != creature.id,
            NPC.alive.is_(True),
            NPC.incapacitated.is_(False),
            NPC.activity != NPCActivity.RESTING.value,
        )
        .order_by(NPC.id)
        .all()
    )
    free = [npc for npc in others if get_active_encounter_for_actor(db, CombatActorType.NPC, npc.id) is None]
    return free[: MAX_PACK - 1]
