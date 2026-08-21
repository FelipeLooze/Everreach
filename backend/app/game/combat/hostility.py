"""NPC hostility: a simple persistent aggression meter, plus autonomous
ambush initiation once the world clock advances.

NPCs decide only *whether* to start a fight here — the Combat Engine
(actions.py/tactics.py/autonomy.py) resolves everything that happens once it
starts, exactly as it does for player-initiated combat. The LLM decides
neither the hostility meter nor the ambush roll.
"""

import random
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import CharacterStatus, CombatActorType, CombatRangeBand
from app.db.models.character import Character
from app.db.models.npc import NPC
from app.game.combat.autonomy import AutonomousCombatResolution, resolve_until_player_turn
from app.game.combat.encounters import (
    CombatantSpec,
    get_active_encounter_for_actor,
    start_encounter,
)
from app.game.combat.turns import roll_initiative

ATTACKED_HOSTILITY = 100
HOSTILE_THRESHOLD = 75
AMBUSH_CHANCE = 0.35


def mark_hostile_from_attack(npc: NPC) -> None:
    """The player attacked this NPC: they become (and stay) hostile.

    No decay — only the backend (never the narrator) changes this value, and
    only ever upward from an attack today.
    """
    npc.hostility = max(npc.hostility, ATTACKED_HOSTILITY)


@dataclass(frozen=True)
class AmbushResult:
    character_id: str
    npc_id: str
    npc_name: str
    encounter_id: str
    resolutions: tuple[AutonomousCombatResolution, ...]


def resolve_ambush_for_character(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    rng: random.Random | None = None,
) -> AmbushResult | None:
    """Give one sufficiently hostile, co-located, uninvolved NPC a chance to
    start a fight with this character.

    Meant to be called once, right after the world clock advances (never
    during the character's own combat turn — those never advance time). At
    most one ambush is started per call, so a single turn never buries the
    player in simultaneous fights.
    """
    if (
        character.status != CharacterStatus.ALIVE.value
        or character.location_id is None
    ):
        return None
    if (
        get_active_encounter_for_actor(db, CombatActorType.CHARACTER, character.id)
        is not None
    ):
        return None

    r = rng or random.Random()

    hostile_npcs = (
        db.query(NPC)
        .filter(
            NPC.campaign_id == campaign_id,
            NPC.location_id == character.location_id,
            NPC.alive.is_(True),
            NPC.incapacitated.is_(False),
            NPC.hostility >= HOSTILE_THRESHOLD,
        )
        .order_by(NPC.id)
        .all()
    )

    for npc in hostile_npcs:
        if (
            get_active_encounter_for_actor(db, CombatActorType.NPC, npc.id)
            is not None
        ):
            continue
        if r.random() >= AMBUSH_CHANCE:
            continue

        encounter = start_encounter(
            db,
            campaign_id,
            character.location_id,
            (
                CombatantSpec(
                    CombatActorType.CHARACTER,
                    character.id,
                    side_key="player",
                    range_band=CombatRangeBand.ENGAGED,
                ),
                CombatantSpec(
                    CombatActorType.NPC,
                    npc.id,
                    side_key="hostile",
                    range_band=CombatRangeBand.ENGAGED,
                ),
            ),
        )
        roll_initiative(db, encounter, rng=r)
        resolutions = tuple(
            resolve_until_player_turn(
                db,
                encounter,
                decision_key_prefix=f"ambush:{encounter.id}",
                rng=r,
            )
        )

        return AmbushResult(
            character_id=character.id,
            npc_id=npc.id,
            npc_name=npc.name,
            encounter_id=encounter.id,
            resolutions=resolutions,
        )

    return None
