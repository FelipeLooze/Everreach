"""What makes a creature fight as its species, not as a generic NPC: its own
damage range (a barn rat bites for 0, an adult boar for 1-4) and a level
bonus to hit and to dodge. Everything else is the ordinary combat engine."""

import json
import random

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType
from app.db.models.npc import NPC


def creature_profile(db: Session, participant) -> dict | None:
    if participant.actor_type != CombatActorType.NPC.value:
        return None
    npc = db.get(NPC, participant.actor_id)
    if npc is None or npc.creature_species is None:
        return None
    return json.loads(npc.profile_json or "{}") or None


def level_bonus(profile: dict) -> int:
    from app.game.creatures.species import CAMPAIGN_DIFFICULTY

    level = int(profile.get("level", 1))
    return max(0, level - 1) + CAMPAIGN_DIFFICULTY.get(level, (1.0, 0, 0))[2]


def damage_roll(profile: dict, critical: bool, rng: random.Random | None) -> int:
    low, high = profile.get("damage", [1, 3])
    rng = rng or random.Random()
    rolled = rng.randint(low, high) if high > 0 else 0
    return rolled + (high if critical else 0)
