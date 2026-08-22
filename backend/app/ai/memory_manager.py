"""Structured memory creation and retrieval; no LLM or vector database required."""
from __future__ import annotations                                              #__future__ Sempre no começo do código

import json
import re
from app.db.models.simulated_player import SimulatedPlayer
from typing import Sequence
from sqlalchemy import case, or_
from sqlalchemy.orm import Session
from app.core.enums import EventType, MemoryOwnerType, TravelIncidentKind
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.db.models.location import Location
from app.db.models.memory import Memory
from app.db.models.npc import NPC


MAX_MEMORY_SUMMARY_CHARS = 500
_STOP_WORDS = {
    "aqui", "aquela", "aquele", "como", "dessa", "desse", "esta", "este",
    "existe", "isso", "onde", "para", "pela", "pelo", "qual", "sobre", "voce",
}


def _clip(text: str, limit: int = MAX_MEMORY_SUMMARY_CHARS) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def create_memory(
    db: Session,
    campaign_id: str,
    owner_type: MemoryOwnerType,
    owner_id: str,
    subject: str,
    summary_text: str,
    *,
    importance: int,
    source_event: WorldEvent,
) -> Memory:
    existing = (
        db.query(Memory)
        .filter(
            Memory.owner_type == owner_type.value,
            Memory.owner_id == owner_id,
            Memory.source_event_id == source_event.id,
        )
        .first()
    )
    if existing is not None:
        return existing

    memory = Memory(
        campaign_id=campaign_id,
        owner_type=owner_type.value,
        owner_id=owner_id,
        subject=subject,
        summary_text=_clip(summary_text),
        source_event_id=source_event.id,
        source_event_ids_json=json.dumps([source_event.id]),
        importance=max(1, min(5, importance)),
    )
    db.add(memory)
    db.flush()
    return memory


def _event_subject(payload: dict, event: WorldEvent) -> str:
    for key, prefix in (
        ("simulated_player_id", "simulated_player"),
        ("group_id", "simulated_player_group"),
        ("npc_id", "npc"),
        ("connection_id", "connection"),
        ("to_location_id", "location"),
        ("location_id", "location"),
        ("quest_id", "quest"),
        ("profession_id", "profession"),
        ("class_id", "class"),
        ("fact_id", "fact"),
    ):
        if payload.get(key):
            return f"{prefix}:{payload[key]}"
    return f"{event.actor_type}:{event.actor_id}" if event.actor_id else "world"


def event_summary_text(db: Session, event: WorldEvent, payload: dict) -> str:
    event_type = event.event_type
    character = db.get(Character, event.actor_id) if event.actor_type == "character" else None
    actor_name = character.name if character is not None else "O personagem"

    if event_type == EventType.WORLD_STARTED.value:
        return (
            f"{actor_name} foi transportado para um lugar desconhecido "
            f"junto de muitas outras pessoas."
        )
    if event_type == EventType.PLAYER_MOVED.value:
        location = db.get(
            Location,
            payload.get("to_location_id"),
        )

        destination_name = (
            location.name
            if location is not None
            else "outro local"
        )

        incident = payload.get("incident")

        if incident == TravelIncidentKind.DELAY.value:
            return (
                f"{actor_name} viajou para {destination_name} "
                f"e sofreu um atraso durante o percurso."
            )

        if incident == TravelIncidentKind.FATIGUE.value:
            return (
                f"{actor_name} viajou para {destination_name} "
                f"e sofreu fadiga adicional durante o percurso."
            )

        return (
            f"{actor_name} viajou para {destination_name}."
        )
    if event_type == EventType.LOCATION_DISCOVERED.value:
        location = db.get(Location, payload.get("location_id"))
        return f"{actor_name} descobriu {location.name if location else 'uma nova localização'}."
    if event_type == EventType.LOCATION_VISITED.value:
        location = db.get(Location, payload.get("location_id"))
        return (
            f"{actor_name} visitou pela primeira vez "
            f"{location.name if location else 'uma nova localização'}."
        )
    if event_type == EventType.CONNECTION_DISCOVERED.value:
        return f"{actor_name} descobriu uma nova rota."
    if event_type == EventType.PLAYER_MET_NPC.value:
        return f"{actor_name} conheceu {payload.get('npc_name', 'uma pessoa')} em {payload.get('location_name', 'sua localização atual')}."
    if event_type == EventType.QUEST_STARTED.value:
        return f"{actor_name} iniciou uma nova missão."
    if event_type == EventType.QUEST_COMPLETED.value:
        return f"{actor_name} concluiu uma missão."
    if event_type == EventType.PLAYER_LEVELED_UP.value:
        return f"{actor_name} alcançou o Level {payload.get('new_level', '?')}."
    if event_type == EventType.PLAYER_PROFESSION_LEVELED_UP.value:
        return (
            f"{actor_name} alcançou o Level {payload.get('new_level', '?')} "
            f"em {payload.get('profession_name', 'uma profissão')}."
        )
    if event_type == EventType.PLAYER_CLASS_OFFERED.value:
        return (
            f"O System disponibilizou a classe "
            f"{payload.get('class_name', 'desconhecida')} para {actor_name}."
        )
    if event_type == EventType.PLAYER_CLASS_ACCEPTED.value:
        return (
            f"{actor_name} aceitou a classe "
            f"{payload.get('class_name', 'desconhecida')}."
        )
    if event_type == EventType.PLAYER_DIED.value:
        return f"{actor_name} morreu permanentemente."
    if event_type == EventType.SIMULATED_PLAYER_DIED.value:
        return (
            f"{payload.get('name', 'Uma pessoa transportada')} morreu permanentemente. "
            f"Causa: {payload.get('cause', 'desconhecida')}."
        )
    if event_type == EventType.SIMULATED_PLAYER_LEVELED_UP.value:
        return f"Alcançou o Level {payload.get('new_level', '?')}."
    if event_type == EventType.SIMULATED_PLAYER_GROUP_CREATED.value:
        return "Formou um grupo temporário de pessoas transportadas."
    if event_type == EventType.SIMULATED_PLAYER_GROUP_DISSOLVED.value:
        return "Um grupo temporário de pessoas transportadas foi dissolvido."
    if event_type == EventType.BOSS_DISCOVERED.value:
        return f"{actor_name} descobriu uma ameaça importante."
    if event_type == EventType.BOSS_DEFEATED.value:
        return f"{actor_name} participou da derrota de uma ameaça importante."
    return f"Evento importante registrado: {event_type}."


def remember_important_event(db: Session, event: WorldEvent) -> list[Memory]:
    """Create traceable owner memories for important structured events."""
    if event.importance < 3:
        return []
    try:
        payload = json.loads(event.payload_json)
    except (json.JSONDecodeError, TypeError):
        payload = {}

    owner_type = {
        "character": MemoryOwnerType.PLAYER,
        "npc": MemoryOwnerType.NPC,
        "simulated_player": MemoryOwnerType.SIMULATED_PLAYER,
        "world": MemoryOwnerType.WORLD,
    }.get(event.actor_type)
    if owner_type is None:
        return []
    owner_id = event.actor_id or event.campaign_id

    memories = [
        create_memory(
            db,
            event.campaign_id,
            owner_type,
            owner_id,
            _event_subject(payload, event),
            event_summary_text(db, event, payload),
            importance=event.importance,
            source_event=event,
        )
    ]
    if event.event_type == EventType.PLAYER_MET_NPC.value and payload.get("npc_id"):
        memories.append(
            create_memory(
                db,
                event.campaign_id,
                MemoryOwnerType.NPC,
                payload["npc_id"],
                f"character:{event.actor_id}",
                (
                    f"Conheceu {payload.get('character_name', 'um forasteiro')} em "
                    f"{payload.get('location_name', 'sua localização atual')}."
                ),
                importance=event.importance,
                source_event=event,
            )
        )
    return memories


def remember_dialogue(
    db: Session,
    source_event: WorldEvent,
    character: Character,
    npc: NPC,
    player_input: str,
    narrative_response: str,
    *,
    importance: int = 2,
) -> tuple[Memory, Memory]:
    spoken = _clip(player_input, 220)
    response = _clip(narrative_response, 220)
    player_memory = create_memory(
        db,
        source_event.campaign_id,
        MemoryOwnerType.PLAYER,
        character.id,
        f"npc:{npc.id}",
        f"Conversou com {npc.name}. Disse: {spoken} Resposta ouvida: {response}",
        importance=importance,
        source_event=source_event,
    )
    npc_memory = create_memory(
        db,
        source_event.campaign_id,
        MemoryOwnerType.NPC,
        npc.id,
        f"character:{character.id}",
        f"{character.name} lhe disse: {spoken} Sua resposta foi: {response}",
        importance=importance,
        source_event=source_event,
    )
    return player_memory, npc_memory


def remember_simulated_player_dialogue(
    db: Session,
    source_event: WorldEvent,
    character: Character,
    simulated_player: SimulatedPlayer,
    player_input: str,
    narrative_response: str,
    *,
    importance: int = 2,
) -> tuple[Memory, Memory]:
    spoken = _clip(
        player_input,
        220,
    )

    response = _clip(
        narrative_response,
        220,
    )

    player_memory = create_memory(
        db,
        source_event.campaign_id,
        MemoryOwnerType.PLAYER,
        character.id,
        f"simulated_player:{simulated_player.id}",
        (
            f"Conversou com {simulated_player.name}. "
            f"Disse: {spoken} "
            f"Resposta ouvida: {response}"
        ),
        importance=importance,
        source_event=source_event,
    )

    simulated_player_memory = create_memory(
        db,
        source_event.campaign_id,
        MemoryOwnerType.SIMULATED_PLAYER,
        simulated_player.id,
        f"character:{character.id}",
        (
            f"{character.name} lhe disse: {spoken} "
            f"Sua resposta foi: {response}"
        ),
        importance=importance,
        source_event=source_event,
    )

    return (
        player_memory,
        simulated_player_memory,
    )


def get_relevant_memories(
    db: Session,
    campaign_id: str,
    owner_type: MemoryOwnerType,
    owner_id: str,
    *,
    subjects: Sequence[str],
    query_text: str,
    limit: int = 4,
) -> list[Memory]:
    if limit <= 0:
        return []
    terms = []
    for term in re.findall(r"\b\w{4,}\b", query_text.casefold()):
        if term not in _STOP_WORDS and term not in terms:
            terms.append(term)
    terms = terms[:8]

    subject_filters = [Memory.subject.in_(subjects)] if subjects else []
    term_filters = [Memory.summary_text.ilike(f"%{term}%") for term in terms]
    relevance_filters = [*subject_filters, *term_filters]
    if not relevance_filters:
        return []

    ordering = []
    if term_filters:
        ordering.append(case((or_(*term_filters), 0), else_=1))
    if subject_filters:
        ordering.append(case((or_(*subject_filters), 0), else_=1))
    ordering.extend((Memory.importance.desc(), Memory.created_at.desc(), Memory.id.desc()))

    return (
        db.query(Memory)
        .filter(
            Memory.campaign_id == campaign_id,
            Memory.owner_type == owner_type.value,
            Memory.owner_id == owner_id,
            or_(*relevance_filters),
        )
        .order_by(*ordering)
        .limit(limit)
        .all()
    )


def get_owner_memories(
    db: Session,
    campaign_id: str,
    owner_type: MemoryOwnerType,
    owner_id: str,
    limit: int = 50,
) -> list[Memory]:
    return (
        db.query(Memory)
        .filter(
            Memory.campaign_id == campaign_id,
            Memory.owner_type == owner_type.value,
            Memory.owner_id == owner_id,
        )
        .order_by(Memory.created_at.desc(), Memory.id.desc())
        .limit(limit)
        .all()
    )


def get_recent_memories(db: Session, campaign_id: str, limit: int = 10) -> list[Memory]:
    """Compatibility query for administrative/world-level inspection."""
    return (
        db.query(Memory)
        .filter(Memory.campaign_id == campaign_id)
        .order_by(Memory.created_at.desc(), Memory.id.desc())
        .limit(limit)
        .all()
    )
