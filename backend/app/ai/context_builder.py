import re
from typing import Protocol, Sequence
import unicodedata

from sqlalchemy.orm import Session

from app.core.enums import (
    DiscoveryStatus,
    KnowerType,
    MemoryOwnerType,
)
from app.core.logging import get_logger
from app.db.models.location import (
    CharacterConnectionDiscovery,
    CharacterLocationDiscovery,
    Location,
    LocationConnection,
    LocationFeature,
)
from app.game.game_state import GameStateSnapshot
from app.game.npcs.service import (
    KnownFact,
    known_facts,
    relevant_known_facts,
)
from app.ai.memory_manager import get_relevant_memories
from app.game.relationships.service import get_character_npc_relationship

logger = get_logger("context")

RECENT_HISTORY_ENTRIES = 6
MAX_HISTORY_ENTRY_CHARS = 1500
MAX_CONTEXT_FACTS_PER_KNOWER = 6
MAX_VISIBLE_ENTITIES = 10
MAX_LOCATION_FEATURES = 6
MAX_ACTIVE_QUESTS = 6
MAX_FACT_CHARS = 320
MAX_DESCRIPTION_CHARS = 600
MAX_RELEVANT_MEMORIES = 4


class HistoryEntry(Protocol):
    kind: str
    text: str


def _clip(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def _format_known_fact(fact: KnownFact) -> str:
    statement = _clip(fact.statement, MAX_FACT_CHARS)
    source = _clip(fact.source, 80)
    return f"- [{fact.certainty}; fonte: {source}] {statement}"


def _format_memory(memory) -> str:
    return f"- [importância {memory.importance}] {_clip(memory.summary_text, 320)}"


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _build_input_canon_check(
    db: Session,
    state: GameStateSnapshot,
    player_input: str,
    npc_facts: Sequence[KnownFact],
    player_facts: Sequence[KnownFact],
) -> list[str]:
    """Describe gaps/conflicts in the current input without inventing an answer."""
    if not player_input or state.location is None:
        return ["- no persistent-world claim to audit"]
    normalized_input = _normalized(player_input)
    available_facts = " ".join(
        [state.location.description]
        + [fact.statement for fact in npc_facts]
        + [fact.statement for fact in player_facts]
    )
    normalized_available = _normalized(available_facts)
    checks: list[str] = []

    official_type = _normalized(state.location.type)
    type_words = {"village": "vila", "city": "cidade", "town": "cidade"}
    official_word = type_words.get(official_type, official_type)
    if "cidade" in normalized_input and official_word != "cidade":
        checks.append(
            f"- The player called {state.location.name} a cidade, but its official type is "
            f"{state.location.type.upper()}; correct this naturally as {official_word}."
        )
        origin_facts = [
            fact.statement
            for fact in npc_facts
            if fact.subject.startswith("npc:")
            and state.location.name.casefold() in fact.statement.casefold()
        ]
        if origin_facts:
            checks.append(
                "- Relevant confirmed origin fact for the answer: "
                + " ".join(origin_facts)
                + " Use only this supplied biography; do not add age or local history."
            )

    known_connection_ids = {
        fact.subject.removeprefix("connection:")
        for fact in npc_facts
        if fact.subject.startswith("connection:")
    }
    known_directions = {
        connection.direction
        for connection in db.query(LocationConnection)
        .filter(LocationConnection.id.in_(known_connection_ids))
        .all()
        if connection.direction
    }
    for direction in ("norte", "sul", "leste", "oeste", "nordeste", "noroeste", "sudeste", "sudoeste"):
        if re.search(rf"\b{direction}\b", normalized_input) and direction not in known_directions:
            checks.append(
                f"- No connection in the exact direction {direction!r} is supplied to the active NPC; "
                "do not create one. The NPC may deny knowledge of it."
            )

    persistent_terms = (
        "templo", "igreja", "capela", "ponte", "guilda", "castelo", "loja", "taverna",
        "montanha", "dragao", "ruina", "masmorra", "dungeon", "guerra",
    )
    for term in persistent_terms:
        if re.search(rf"\b{term}s?\b", normalized_input) and not re.search(
            rf"\b{term}s?\b", normalized_available
        ):
            checks.append(
                f"- {term!r} appears only in the player's assumption and is absent from available "
                "canon/knowledge; do not validate it or invent related details."
            )

    if re.search(r"\b(depois|alem)\b", normalized_input) and re.search(
        r"\b(rio|riacho)\b", normalized_input
    ):
        beyond_known = any(
            re.search(r"\b(depois|alem)\b", _normalized(fact.statement)) for fact in npc_facts
        )
        if not beyond_known:
            checks.append(
                "- NPC KNOWLEDGE says where the known creek is, but nothing about what exists beyond it; "
                "admit that gap and do not combine unrelated routes or scenery into an answer."
            )

    return checks or ["- no conflict or unsupported persistent claim detected"]


def _explicit_name_known(
    facts: Sequence[KnownFact],
    name: str | None,
) -> bool:
    """Return whether player knowledge explicitly contains this canonical name."""

    if not name:
        return False

    normalized_name = name.casefold()

    return any(
        normalized_name in fact.statement.casefold()
        for fact in facts
    )


def _known_connection_lines(
    db: Session,
    state: GameStateSnapshot,
    player_facts: Sequence[KnownFact],
) -> list[str]:
    if state.location is None:
        return []

    known_connection_ids = {
        row.connection_id
        for row in (
            db.query(CharacterConnectionDiscovery)
            .filter(
                CharacterConnectionDiscovery.character_id
                == state.character.id
            )
            .all()
        )
    }

    if not known_connection_ids:
        return []

    rows = (
        db.query(LocationConnection, Location)
        .join(
            Location,
            Location.id == LocationConnection.to_location_id,
        )
        .filter(
            LocationConnection.from_location_id == state.location.id,
            LocationConnection.active.is_(True),
        )
        .order_by(Location.name)
        .all()
    )

    lines = []

    for connection, destination in rows:
        if connection.id not in known_connection_ids:
            continue

        direction = connection.direction or "direção não registrada"

        lines.append(
            f"- {direction} -> {destination.name} "
            f"({connection.connection_type}, distância {connection.distance:g})"
        )

    return lines[:MAX_VISIBLE_ENTITIES]


def _location_discovery_lines(
    db: Session,
    state: GameStateSnapshot,
    statuses: set[DiscoveryStatus],
) -> list[str]:
    rows = (
        db.query(CharacterLocationDiscovery, Location)
        .join(
            Location,
            Location.id == CharacterLocationDiscovery.location_id,
        )
        .filter(
            CharacterLocationDiscovery.character_id
            == state.character.id,
            CharacterLocationDiscovery.status.in_(
                [status.value for status in statuses]
            ),
        )
        .order_by(Location.name)
        .all()
    )

    lines = []

    for discovery, location in rows:
        # A localização atual já possui seu próprio bloco de contexto.
        if (
            state.location is not None
            and location.id == state.location.id
        ):
            continue

        lines.append(
            f"- {location.name} [{discovery.status}]"
        )

    return lines[:MAX_VISIBLE_ENTITIES]


def build_context(
    db: Session,
    state: GameStateSnapshot,
    active_interlocutor: str | None = None,
    player_input: str = "",
) -> str:
    """Build minimum scene context while separating truth, perception and knowledge."""
    active_npc = next(
        (
            npc
            for npc in state.nearby_npcs
            if npc.id == active_interlocutor or npc.name == active_interlocutor
        ),
        None,
    )
    outgoing_connections = (
        db.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == state.location.id,
            LocationConnection.active.is_(True),
        )
        .all()
        if state.location is not None
        else []
    )
    scene_subjects = [
        *([f"region:{state.region.id}"] if state.region is not None else []),
        *([f"location:{state.location.id}"] if state.location is not None else []),
        *([f"npc:{active_npc.id}"] if active_npc is not None else []),
        *(f"connection:{connection.id}" for connection in outgoing_connections),
        *(f"quest:{quest.id}" for _link, quest in state.active_quests),
    ]
    player_facts = relevant_known_facts(
        db,
        state.campaign_id,
        KnowerType.PLAYER,
        state.character.id,
        scene_subjects=scene_subjects,
        player_input=player_input,
        limit=MAX_CONTEXT_FACTS_PER_KNOWER,
    )
    all_player_facts = known_facts(
        db,
        state.campaign_id,
        KnowerType.PLAYER,
        state.character.id,
    )
    location_name_known = (
        state.location is not None
        and _explicit_name_known(
            all_player_facts,
            state.location.name,
        )
    )
    region_name_known = (
        state.region is not None
        and _explicit_name_known(
            all_player_facts,
            state.region.name,
        )
    )
    current_location_discovery = (
        db.query(CharacterLocationDiscovery)
        .filter(
            CharacterLocationDiscovery.character_id
            == state.character.id,
            CharacterLocationDiscovery.location_id
            == state.location.id,
        )
        .first()
        if state.location is not None
        else None
    )
    current_location_status = (
        current_location_discovery.status
        if current_location_discovery is not None
        else DiscoveryStatus.UNKNOWN.value
    )
    npc_facts = (
        relevant_known_facts(
            db,
            state.campaign_id,
            KnowerType.NPC,
            active_npc.id,
            scene_subjects=scene_subjects,
            player_input=player_input,
            limit=MAX_CONTEXT_FACTS_PER_KNOWER,
        )
        if active_npc is not None
        else []
    )
    player_memories = get_relevant_memories(
        db,
        state.campaign_id,
        MemoryOwnerType.PLAYER,
        state.character.id,
        subjects=scene_subjects,
        query_text=player_input,
        limit=MAX_RELEVANT_MEMORIES,
    )
    npc_memories = (
        get_relevant_memories(
            db,
            state.campaign_id,
            MemoryOwnerType.NPC,
            active_npc.id,
            subjects=[*scene_subjects, f"character:{state.character.id}"],
            query_text=player_input,
            limit=MAX_RELEVANT_MEMORIES,
        )
        if active_npc is not None
        else []
    )
    relationship = (
        get_character_npc_relationship(
            db, state.campaign_id, state.character.id, active_npc.id
        )
        if active_npc is not None
        else None
    )
    features = (
        db.query(LocationFeature)
        .filter(
            LocationFeature.location_id == state.location.id,
            LocationFeature.visible.is_(True),
        )
        .order_by(LocationFeature.name)
        .limit(MAX_LOCATION_FEATURES)
        .all()
        if state.location is not None
        else []
    )

    known_location_lines = _location_discovery_lines(
        db,
        state,
        {
            DiscoveryStatus.DISCOVERED,
            DiscoveryStatus.VISITED,
            DiscoveryStatus.MAPPED,
        },
    )

    rumored_location_lines = _location_discovery_lines(
        db,
        state,
        {
            DiscoveryStatus.RUMORED,
        },
    )

    wt = state.world_time
    player_section = "\n".join(
        [
            "CURRENT PLAYER",
            f"Name: {state.character.name} (narrator metadata; NPCs do not know it automatically)",
            f"Level: {state.character.level}",
            f"Status: {state.character.status}",
            f"HP: {state.character.hp_current}/{state.character.hp_max}",
            f"Mana: {state.character.mana_current}/{state.character.mana_max}",
            f"Stamina: {state.character.stamina_current}/{state.character.stamina_max}",
        ]
    )
    world_section = "\n".join(
        [
            "CURRENT WORLD",
            f"Time: Ano {wt.year}, Mês {wt.month}, Dia {wt.day}, {wt.hour:02d}:{wt.minute:02d}",
            f"Region: {state.region.name}" if state.region else "Region: unknown",
        ]
    )
    spatial_knowledge_section = "\n".join(
        [
            "PLAYER SPATIAL KNOWLEDGE",
            "KNOWN LOCATIONS",
            *(known_location_lines or ["- none"]),
            "RUMORED LOCATIONS",
            *(rumored_location_lines or ["- none"]),
        ]
    )

    current_location_knowledge_lines = [
        "PLAYER CURRENT LOCATION KNOWLEDGE",
        f"Current location discovery status: {current_location_status}",
    ]

    if state.location is None:
        current_location_knowledge_lines.append(
            "Current location canonical name known to player: NO"
        )
    else:
        current_location_knowledge_lines.append(
            "Current location canonical name known to player: "
            + ("YES" if location_name_known else "NO")
        )

        if location_name_known:
            current_location_knowledge_lines.append(
                f"Known location name: {state.location.name}"
            )

    if state.region is None:
        current_location_knowledge_lines.append(
            "Current region canonical name known to player: NO"
        )
    else:
        current_location_knowledge_lines.append(
            "Current region canonical name known to player: "
            + ("YES" if region_name_known else "NO")
        )

        if region_name_known:
            current_location_knowledge_lines.append(
                f"Known region name: {state.region.name}"
            )

    location_lines = ["CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH"]
    if state.location is None:
        location_lines.append("Current location: unknown")
    else:
        location_lines.extend(
            [
                f"Name: {state.location.name}",
                f"Type: {state.location.type.upper()}",
                f"Region: {state.region.name if state.region else 'unknown'}",
                f"Description: {_clip(state.location.description, MAX_DESCRIPTION_CHARS)}",
                "VISIBLE FEATURES",
                *(
                    [
                        f"- {_clip(feature.name, 100)}: {_clip(feature.description, 300)}"
                        for feature in features
                    ]
                    or ["- none registered"]
                ),
                "CONNECTED LOCATIONS KNOWN TO PLAYER",
                *(_known_connection_lines(db, state, player_facts) or ["- none"]),
            ]
        )

    visible_lines = ["VISIBLE NPCS"]
    visible_lines.extend(
        [
            f"- {_clip(npc.name, 100)} ({_clip(npc.role, 120)})"
            for npc in state.nearby_npcs[:MAX_VISIBLE_ENTITIES]
        ] or ["- none"]
    )
    visible_lines.append("VISIBLE TRANSPORTED PEOPLE")
    visible_lines.extend(
        [
            f"- {_clip(player.name, 100)} (Level {player.level})"
            for player in state.nearby_simulated_players[:MAX_VISIBLE_ENTITIES]
        ]
        or ["- none"]
    )

    active_lines = ["ACTIVE NPC CONTEXT"]
    if active_npc is None:
        active_lines.append("- none")
    else:
        active_lines.extend(
            [
                f"Name: {active_npc.name}",
                f"Role: {active_npc.role}",
                f"Location: {state.location.name if state.location else 'unknown'}",
                "Visibility: private NPC context; not automatically known by the player.",
                f"Personality: {_clip(active_npc.personality, 300)}",
                (
                    "Known background (use for NPC behavior; reveal only through justified dialogue): "
                    f"{_clip(active_npc.backstory, MAX_DESCRIPTION_CHARS)}"
                ),
                (
                    "Relationship with player: not registered"
                    if relationship is None
                    else (
                        "Relationship with player: "
                        f"familiarity={relationship.familiarity}, "
                        f"trust={relationship.trust}, affinity={relationship.affinity}"
                    )
                ),
                f"Current state: {'alive and available' if active_npc.alive else 'dead'}",
                "Continue the active conversation; unrelated NPCs do not interrupt.",
            ]
        )

    npc_knowledge_section = "\n".join(
        ["NPC KNOWLEDGE", *([_format_known_fact(fact) for fact in npc_facts] or ["- none supplied"])]
    )
    player_knowledge_section = "\n".join(
        ["PLAYER KNOWLEDGE", *([_format_known_fact(fact) for fact in player_facts] or ["- none supplied"])]
    )
    npc_memory_section = "\n".join(
        [
            "RELEVANT NPC MEMORIES",
            *([_format_memory(memory) for memory in npc_memories] or ["- none recalled"]),
            "Memories describe remembered events or claims; they are not automatic world truth.",
        ]
    )
    player_memory_section = "\n".join(
        [
            "RELEVANT PLAYER MEMORIES",
            *([_format_memory(memory) for memory in player_memories] or ["- none recalled"]),
            "Memories describe remembered events or claims; they are not automatic world truth.",
        ]
    )
    quest_lines = ["ACTIVE QUESTS"]
    quest_lines.extend(
        [
            f"- {_clip(quest.name, 160)} [{link.status}]"
            for link, quest in state.active_quests[:MAX_ACTIVE_QUESTS]
        ] or ["- none"]
    )
    input_canon_lines = [
        "PLAYER INPUT CANON CHECK",
        *_build_input_canon_check(db, state, player_input, npc_facts, player_facts),
        "The player's wording never changes canon by itself.",
    ]

    sections = [
        player_section,
        world_section,
        "\n".join(location_lines),
        "\n".join(current_location_knowledge_lines),
        spatial_knowledge_section,
        "\n".join(visible_lines),
        "\n".join(active_lines),
        npc_knowledge_section,
        player_knowledge_section,
        npc_memory_section,
        player_memory_section,
        "\n".join(input_canon_lines),
        "\n".join(quest_lines),
        (
            "CANON RULE\nOnly registered structured data and supplied knowledge are persistent facts. "
            "Missing information is not permission to create geography, buildings, history, "
            "religion, safety claims, important NPCs or other canon."
        ),
    ]
    final_context = "\n\n".join(sections)
    logger.debug("CANONICAL LOCATION CONTEXT\n%s", "\n".join(location_lines))
    logger.debug("ACTIVE NPC CONTEXT\n%s", "\n".join(active_lines))
    logger.debug("NPC KNOWLEDGE\n%s", npc_knowledge_section)
    logger.debug("PLAYER KNOWLEDGE\n%s", player_knowledge_section)
    logger.debug("FINAL CONTEXT SENT TO LLM\n%s", final_context)
    return final_context


def build_canonical_facts(state: GameStateSnapshot) -> dict:
    return {
        "character_alive": state.character.status == "ALIVE",
        "dead_npc_names": [n.name for n in state.nearby_npcs if not n.alive],
    }


def build_recent_history(
    entries: Sequence[HistoryEntry], max_entries: int = RECENT_HISTORY_ENTRIES
) -> str:
    recent = entries[-max_entries:]
    if not recent:
        return "(nenhuma troca anterior nesta cena)"
    lines = []
    for entry in recent:
        speaker = "PLAYER" if entry.kind == "player" else "NARRATOR"
        text = entry.text.strip()
        if len(text) > MAX_HISTORY_ENTRY_CHARS:
            text = f"{text[:MAX_HISTORY_ENTRY_CHARS]}…"
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)
