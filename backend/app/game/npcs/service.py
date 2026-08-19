import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from sqlalchemy import case, or_
from sqlalchemy.orm import Session
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.character import Character
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.npc import NPC
from app.db.models.event import WorldEvent
from app.services.event_log import log_event
from app.game.relationships.service import get_character_npc_relationship
from app.db.models.location import Location, LocationConnection
from app.game.discovery.service import (
    discover_connection,
    set_location_discovery,
)
from app.core.enums import (
    DiscoveryStatus,
    EventType,
    KnowledgeCertainty,
    KnowerType,
    MemoryOwnerType,
    NPCActivity,
    CharacterStatus,
    SimulatedPlayerStatus,
)

_CONVERSATION_BOUNDARY_EVENTS = (
    EventType.PLAYER_MET_NPC.value,
    EventType.PLAYER_TALKED_TO_NPC.value,
    EventType.PLAYER_MOVED.value,
    EventType.PLAYER_RESTED.value,
    EventType.PLAYER_DIED.value,
    EventType.WORLD_STARTED.value,
)


def npcs_at_location(
    db: Session,
    location_id: str,
) -> list[NPC]:
    return (
        db.query(NPC)
        .filter(
            NPC.location_id == location_id,
            NPC.alive.is_(True),
            NPC.activity != NPCActivity.RESTING.value,
        )
        .order_by(NPC.id)
        .all()
    )

@dataclass(frozen=True)
class KnownFact:
    subject: str
    fact_key: str
    statement: str
    source: str
    certainty: str
    discovered_at: datetime


def known_facts(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
) -> list[KnownFact]:
    """Return only facts explicitly associated with this exact knower."""
    rows = (
        db.query(KnowledgeFact, KnowledgeKnower)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
        )
        .order_by(KnowledgeKnower.discovered_at, KnowledgeFact.fact_key)
        .all()
    )
    return [
        KnownFact(
            subject=fact.subject,
            fact_key=fact.fact_key,
            statement=fact.statement,
            source=link.source,
            certainty=link.certainty,
            discovered_at=link.discovered_at,
        )
        for fact, link in rows
    ]


_SEARCH_STOP_WORDS = {
    "aqui", "aquela", "aquele", "como", "conhece", "dessa", "desse", "esta",
    "este", "existe", "isso", "onde", "para", "pela", "pelo", "qual", "sobre",
    "senhor", "senhora", "alguma", "algum", "voce",
}


def relevant_known_facts(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    *,
    scene_subjects: Sequence[str],
    player_input: str,
    limit: int = 6,
) -> list[KnownFact]:
    """Fetch a small, deterministic set of facts relevant to the current scene.

    Scene-scoped facts have priority. Facts outside the scene are considered only
    when the player's current wording overlaps their statement. This keeps remote
    lore and secrets out of the LLM context without treating absence as permission
    to invent an answer.
    """
    if limit <= 0:
        return []

    terms = []
    for term in re.findall(r"\b\w{4,}\b", player_input.casefold()):
        if term not in _SEARCH_STOP_WORDS and term not in terms:
            terms.append(term)
    terms = terms[:8]

    relevance_filters = []
    if scene_subjects:
        relevance_filters.append(KnowledgeFact.subject.in_(scene_subjects))
    term_filters = [KnowledgeFact.statement.ilike(f"%{term}%") for term in terms]
    relevance_filters.extend(term_filters)
    if not relevance_filters:
        return []

    ordering = []
    if term_filters:
        ordering.append(case((or_(*term_filters), 0), else_=1))
    if scene_subjects:
        ordering.append(case((KnowledgeFact.subject.in_(scene_subjects), 0), else_=1))
    ordering.extend((KnowledgeKnower.discovered_at.desc(), KnowledgeFact.fact_key))
    rows = (
        db.query(KnowledgeFact, KnowledgeKnower)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
            or_(*relevance_filters),
        )
        .order_by(*ordering)
        .limit(limit)
        .all()
    )
    return [
        KnownFact(
            subject=fact.subject,
            fact_key=fact.fact_key,
            statement=fact.statement,
            source=link.source,
            certainty=link.certainty,
            discovered_at=link.discovered_at,
        )
        for fact, link in rows
    ]

def certainty_rank(
    certainty: KnowledgeCertainty,
) -> int:
    return {
        KnowledgeCertainty.RUMOR: 1,
        KnowledgeCertainty.BELIEVED: 2,
        KnowledgeCertainty.CONFIRMED: 3,
    }[certainty]

def knows(db: Session, knower_type: KnowerType, knower_id: str, fact_key: str, campaign_id: str) -> bool:
    """A knower only knows a fact if there is an explicit KnowledgeKnower row.
    Absence means ignorance — NPCs/players never automatically know world truths."""
    fact = (
        db.query(KnowledgeFact)
        .filter(KnowledgeFact.campaign_id == campaign_id, KnowledgeFact.fact_key == fact_key)
        .first()
    )
    if fact is None:
        return False

    return (
        db.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
        )
        .first()
        is not None
    )


def teach_fact(
    db: Session,
    campaign_id: str,
    fact_key: str,
    knower_type: KnowerType,
    knower_id: str,
    *,
    source: str = "system",
    certainty: KnowledgeCertainty = KnowledgeCertainty.CONFIRMED,
) -> None:
    fact = (
        db.query(KnowledgeFact)
        .filter(KnowledgeFact.campaign_id == campaign_id, KnowledgeFact.fact_key == fact_key)
        .first()
    )
    if fact is None:
        raise ValueError(f"Unknown fact_key '{fact_key}' for campaign {campaign_id}")

    exists = (
        db.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type == knower_type.value,
            KnowledgeKnower.knower_id == knower_id,
        )
        .first()
    )

    if exists:
        current_certainty = KnowledgeCertainty(
            exists.certainty
        )

        if (
            certainty_rank(certainty)
            <= certainty_rank(
                current_certainty
            )
        ):
            return

        exists.certainty = certainty.value
        exists.source = source
        db.flush()

    else:
        db.add(
            KnowledgeKnower(
                fact_id=fact.id,
                knower_type=knower_type.value,
                knower_id=knower_id,
                source=source,
                certainty=certainty.value,
            )
        )
        db.flush()

    if (
        knower_type == KnowerType.PLAYER
        and certainty == KnowledgeCertainty.CONFIRMED
        and fact.subject.startswith("connection:")
    ):
        connection_id = fact.subject.removeprefix("connection:")

        connection = db.get(
            LocationConnection,
            connection_id,
        )

        if connection is not None:
            _connection_discovery, connection_changed = discover_connection(
                db,
                knower_id,
                connection.id,
            )

            _location_discovery, location_changed = set_location_discovery(
                db,
                knower_id,
                connection.to_location_id,
                DiscoveryStatus.DISCOVERED,
            )

            if connection_changed:
                log_event(
                    db,
                    campaign_id,
                    EventType.CONNECTION_DISCOVERED,
                    actor_type="character",
                    actor_id=knower_id,
                    payload={
                        "connection_id": connection.id,
                        "from_location_id": connection.from_location_id,
                        "to_location_id": connection.to_location_id,
                        "direction": connection.direction,
                        "connection_type": connection.connection_type,
                        "source": source,
                    },
                )

            if location_changed:
                log_event(
                    db,
                    campaign_id,
                    EventType.LOCATION_DISCOVERED,
                    actor_type="character",
                    actor_id=knower_id,
                    importance=2,
                    payload={
                        "location_id": connection.to_location_id,
                        "source": source,
                    },
                )


def meet_npc(db: Session, campaign_id: str, character_id: str, npc_id: str) -> NPC:
    npc = db.get(NPC, npc_id)
    if npc is None:
        raise ValueError(f"Unknown NPC {npc_id}")

    character = db.get(Character, character_id)
    location = db.get(Location, npc.location_id)
    first_meeting = (
        get_character_npc_relationship(db, campaign_id, character_id, npc_id) is None
    )
    log_event(
        db,
        campaign_id,
        EventType.PLAYER_MET_NPC if first_meeting else EventType.PLAYER_TALKED_TO_NPC,
        actor_type="character",
        actor_id=character_id,
        payload={
            "npc_id": npc_id,
            "npc_name": npc.name,
            "character_name": character.name if character else "um forasteiro",
            "location_id": npc.location_id,
            "location_name": location.name if location else "local desconhecido",
        },
    )
    return npc

def _knower_location_id(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
) -> str | None:
    if knower_type == KnowerType.PLAYER:
        character = db.get(
            Character,
            knower_id,
        )

        if (
            character is None
            or character.campaign_id != campaign_id
            or character.status
            != CharacterStatus.ALIVE.value
        ):
            return None

        return character.location_id

    if knower_type == KnowerType.NPC:
        npc = db.get(
            NPC,
            knower_id,
        )

        if (
            npc is None
            or npc.campaign_id != campaign_id
            or not npc.alive
        ):
            return None

        return npc.location_id

    if (
        knower_type
        == KnowerType.SIMULATED_PLAYER
    ):
        simulated_player = db.get(
            SimulatedPlayer,
            knower_id,
        )

        if (
            simulated_player is None
            or simulated_player.campaign_id
            != campaign_id
            or simulated_player.status
            != SimulatedPlayerStatus.ACTIVE.value
        ):
            return None

        return simulated_player.location_id

    return None

def propagate_fact(
    db: Session,
    campaign_id: str,
    fact_key: str,
    from_type: KnowerType,
    from_id: str,
    to_type: KnowerType,
    to_id: str,
    *,
    certainty: KnowledgeCertainty | None = None,
) -> bool:
    """Transfer one explicit fact; narrative prose can never call this implicitly."""
    fact = (
        db.query(KnowledgeFact)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeFact.fact_key == fact_key,
        )
        .first()
    )
    if fact is None:
        raise ValueError(f"Unknown fact_key '{fact_key}' for campaign {campaign_id}")

    source_link = (
        db.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type == from_type.value,
            KnowledgeKnower.knower_id == from_id,
        )
        .first()
    )
    if source_link is None:
        raise ValueError("A fonte não conhece o fato que tentou compartilhar.")

    source_certainty = KnowledgeCertainty(
        source_link.certainty
    )

    target_certainty = (
        certainty
        if certainty is not None
        else source_certainty
    )

    target_link = (
        db.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type
            == to_type.value,
            KnowledgeKnower.knower_id
            == to_id,
        )
        .first()
    )

    if target_link is not None:
        current_target_certainty = (
            KnowledgeCertainty(
                target_link.certainty
            )
        )

        if (
            certainty_rank(
                target_certainty
            )
            <= certainty_rank(
                current_target_certainty
            )
        ):
            return False

    teach_fact(
        db,
        campaign_id,
        fact_key,
        to_type,
        to_id,
        source=f"{from_type.value.lower()}:{from_id}",
        certainty=target_certainty,
    )
    event = log_event(
        db,
        campaign_id,
        EventType.KNOWLEDGE_PROPAGATED,
        actor_type=from_type.value.lower(),
        actor_id=from_id,
        payload={
            "fact_id": fact.id,
            "fact_key": fact.fact_key,
            "to_type": to_type.value,
            "to_id": to_id,
            "source_certainty": (
                source_certainty.value
            ),
            "target_certainty": (
                target_certainty.value
            ),
        },
    )

    from app.ai.memory_manager import create_memory

    owner_type = MemoryOwnerType(to_type.value)
    create_memory(
        db,
        campaign_id,
        owner_type,
        to_id,
        fact.subject,
        f"Aprendeu: {fact.statement}",
        importance=3,
        source_event=event,
    )
    return True

def propagate_fact_locally(
    db: Session,
    campaign_id: str,
    fact_key: str,
    from_type: KnowerType,
    from_id: str,
    to_type: KnowerType,
    to_id: str,
    *,
    certainty: KnowledgeCertainty | None = None,
) -> bool:
    source_location_id = _knower_location_id(
        db,
        campaign_id,
        from_type,
        from_id,
    )

    target_location_id = _knower_location_id(
        db,
        campaign_id,
        to_type,
        to_id,
    )

    if (
        source_location_id is None
        or target_location_id is None
        or source_location_id
        != target_location_id
    ):
        raise ValueError(
            "A fonte e o destino precisam estar "
            "ativos e no mesmo local."
        )

    return propagate_fact(
        db,
        campaign_id,
        fact_key,
        from_type,
        from_id,
        to_type,
        to_id,
        certainty=certainty,
    )

def get_active_interlocutor(
    db: Session,
    campaign_id: str,
    character_id: str,
    location_id: str,
) -> NPC | None:
    """Return the NPC in the character's current structured conversation.

    Narrator prose is presentation, not state. The most recent scene-boundary event
    decides whether a conversation remains active, so direct follow-up speech works
    even when the narrator did not repeat the NPC's name.
    """
    event = (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign_id,
            WorldEvent.actor_type == "character",
            WorldEvent.actor_id == character_id,
            WorldEvent.event_type.in_(_CONVERSATION_BOUNDARY_EVENTS),
        )
        .order_by(WorldEvent.created_at.desc(), WorldEvent.id.desc())
        .first()
    )
    if event is None or event.event_type not in (
        EventType.PLAYER_MET_NPC.value,
        EventType.PLAYER_TALKED_TO_NPC.value,
    ):
        return None

    try:
        npc_id = json.loads(event.payload_json).get("npc_id")
    except (json.JSONDecodeError, TypeError):
        return None
    if not npc_id:
        return None

    npc = db.get(NPC, npc_id)
    if (
        npc is None
        or npc.campaign_id != campaign_id
        or npc.location_id != location_id
        or not npc.alive
        or npc.activity == NPCActivity.RESTING.value
    ):
        return None
    return npc
