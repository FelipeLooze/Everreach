"""Phase 17D — Exploration & Discovery.

Exploration is authoritative, same pattern as every other Game Engine
resolution (dice in app.game.dice, never the LLM): explore_current_location
decides what, if anything, gets found; the caller only narrates the
already-resolved result.

PASSIVE vs ACTIVE (spec): arriving somewhere via app.game.travel.service
.move_character already reveals the destination itself (VISITED,
ensure_location_materialized) — that existing behavior IS passive
discovery of the place actually arrived at, and needed no change here.
This module is the ACTIVE counterpart — a character who deliberately
searches near their current location may find a connection nobody has
discovered yet. Nothing here adds a "reveal everything within radius R"
mechanic (spec explicitly rejects that): exploring the same location
twice is not doubly rewarding once nothing undiscovered is left nearby,
and a single attempt reveals at most one thing, weighted toward the
easier/safer connections a character would plausibly notice first
(spec: "Do not force everything through explicit Search commands" is
about NOT gating passive discovery behind an action — it does not mean
active search must always succeed).

Reuses, never duplicates: LocationConnection (Phase 1) is the existing
"what's near here" graph; CharacterConnectionDiscovery/set_location_discovery
(Phase 1/15) are the existing per-character discovery writers; d20
(app.game.dice) is the existing dice primitive; grant_geographic_knowledge
(17A) is how the newly found place's bare existence becomes real,
character-specific knowledge (not full detail — a character who just
found a route doesn't automatically know the destination's name,
dangers, or services; those are separate aspects, taught elsewhere).

Deliberately NOT built here (later subphases, explicitly listed in the
spec as future dependencies, not this foundation's job): terrain/
weather/visibility modeling, and wiring search success to attributes/
techniques/profession (17Q — Exploration Progression Integration).
DC_SEARCH is a flat, documented placeholder until 17Q gives it a real
character-dependent modifier. No LLM/engine ActionIntentType wiring
either — this is the authoritative primitive a future EXPLORE intent
(or 17I's NPC/organization expeditions) will call; wiring the
player-facing action itself belongs with narrator-context work (17P).
"""

import random
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import DiscoverySignificance, EventType, GeographicKnowledgeAspect, KnowerType
from app.db.models.character import Character
from app.db.models.location import CharacterConnectionDiscovery, Location, LocationConnection
from app.game.dice import d20
from app.game.discovery.service import discover_connection, set_location_discovery
from app.game.exploration.discovery_significance import assess_location_discovery_significance
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.time.clock import advance_world_time
from app.services.event_log import log_event

EXPLORATION_MINUTES = 90
DC_SEARCH = 12


@dataclass
class ExplorationOutcome:
    success: bool
    minutes_spent: int
    found_connection_id: str | None = None
    found_location_id: str | None = None
    significance: DiscoverySignificance | None = None


def _undiscovered_outgoing_connections(db: Session, character_id: str, location_id: str) -> list[LocationConnection]:
    known_connection_ids = {
        row[0]
        for row in db.query(CharacterConnectionDiscovery.connection_id)
        .filter(CharacterConnectionDiscovery.character_id == character_id)
        .all()
    }
    connections = (
        db.query(LocationConnection)
        .filter(LocationConnection.from_location_id == location_id, LocationConnection.active.is_(True))
        .all()
    )
    return [c for c in connections if c.id not in known_connection_ids]


def explore_current_location(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    rng: random.Random | None = None,
) -> ExplorationOutcome:
    """Nothing left to find near here returns success=False with no
    discovery, same as a failed search roll — from the outside these two
    "nothing happened" cases are indistinguishable, matching how a real
    search that turns up empty doesn't tell you whether there was
    genuinely nothing there."""
    candidates = _undiscovered_outgoing_connections(db, character.id, character.location_id)

    advance_world_time(db, campaign_id, EXPLORATION_MINUTES)

    if not candidates:
        log_event(
            db, campaign_id, EventType.EXPLORATION_ATTEMPTED,
            actor_type="character", actor_id=character.id,
            payload={"location_id": character.location_id, "found": False, "reason": "nothing_nearby"},
        )
        return ExplorationOutcome(success=False, minutes_spent=EXPLORATION_MINUTES)

    result = d20(rng=rng)
    if result.total < DC_SEARCH:
        log_event(
            db, campaign_id, EventType.EXPLORATION_ATTEMPTED,
            actor_type="character", actor_id=character.id,
            payload={"location_id": character.location_id, "found": False, "reason": "search_failed", "roll": result.total},
        )
        return ExplorationOutcome(success=False, minutes_spent=EXPLORATION_MINUTES)

    picker = rng or random
    weights = [1.0 / (1 + connection.danger) for connection in candidates]
    found = picker.choices(candidates, weights=weights, k=1)[0]

    discover_connection(db, character.id, found.id)
    destination = db.get(Location, found.to_location_id)
    set_location_discovery(db, character.id, destination.id, "DISCOVERED")
    significance = assess_location_discovery_significance(destination)

    ensure_geographic_fact(
        db, campaign_id, "location", destination.id, GeographicKnowledgeAspect.EXISTENCE,
        f"Existe um caminho levando a {destination.name}.",
    )
    grant_geographic_knowledge(
        db, campaign_id, KnowerType.PLAYER, character.id,
        "location", destination.id, GeographicKnowledgeAspect.EXISTENCE,
        source="exploração ativa",
    )

    log_event(
        db, campaign_id, EventType.CONNECTION_DISCOVERED,
        actor_type="character", actor_id=character.id,
        payload={
            "connection_id": found.id,
            "from_location_id": found.from_location_id,
            "to_location_id": found.to_location_id,
            "source": "exploration",
        },
    )
    log_event(
        db, campaign_id, EventType.LOCATION_DISCOVERED,
        actor_type="character", actor_id=character.id,
        payload={"location_id": destination.id, "source": "exploration", "significance": significance.value},
    )
    log_event(
        db, campaign_id, EventType.EXPLORATION_ATTEMPTED,
        actor_type="character", actor_id=character.id,
        payload={"location_id": character.location_id, "found": True, "connection_id": found.id, "roll": result.total},
    )

    return ExplorationOutcome(
        success=True,
        minutes_spent=EXPLORATION_MINUTES,
        found_connection_id=found.id,
        found_location_id=destination.id,
        significance=significance,
    )
