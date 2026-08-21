import re
from typing import Protocol, Sequence
import unicodedata

from sqlalchemy.orm import Session
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.core.enums import (
    DiscoveryStatus,
    KnowerType,
    MemoryOwnerType,
    SimulatedPlayerStatus,
)
from app.core.logging import get_logger
from app.db.models.location import (
    CharacterConnectionDiscovery,
    CharacterLocationDiscovery,
    Location,
    LocationConnection,
    LocationFeature,
)
from app.game.combat.context import build_active_encounter_snapshot
from app.game.game_state import GameStateSnapshot
from app.game.items.context import build_narrator_inventory_context
from app.game.npcs.service import (
    KnownFact,
    known_facts,
    relevant_known_facts,
)
from app.ai.memory_manager import get_relevant_memories
from app.game.relationships.service import (
    get_character_npc_relationship,
    get_character_simulated_player_relationship,
    simulated_player_relationship_behavior_guidance,
)
from app.game.players.groups import active_group_for_player


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

        destination_name = (
            destination.name
            if _explicit_name_known(player_facts, destination.name)
            else "Local desconhecido"
        )

        lines.append(
            f"- {direction} -> {destination_name} "
            f"({connection.connection_type}, distância {connection.distance:g})"
        )

    return lines[:MAX_VISIBLE_ENTITIES]


def _location_discovery_lines(
    db: Session,
    state: GameStateSnapshot,
    statuses: set[DiscoveryStatus],
    player_facts: Sequence[KnownFact],
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

        display_name = (
            location.name
            if _explicit_name_known(player_facts, location.name)
            else "Local desconhecido"
        )

        lines.append(
            f"- {display_name} [{discovery.status}]"
        )

    return lines[:MAX_VISIBLE_ENTITIES]


def _resolve_active_npc(
    db: Session,
    state: GameStateSnapshot,
    active_interlocutor: str | None,
) -> NPC | None:
    active_npc = next(
        (
            npc
            for npc in state.nearby_npcs
            if npc.id == active_interlocutor or npc.name == active_interlocutor
        ),
        None,
    )
    # The interlocutor of the action may have become unavailable after
    # the action advanced world time. Keep that NPC available to the
    # narrator for this completed interaction without putting them back
    # into the current visible scene.
    if active_npc is None and active_interlocutor:
        candidate = db.get(NPC, active_interlocutor)

        if (
            candidate is not None
            and candidate.campaign_id == state.campaign_id
            and state.location is not None
            and candidate.location_id == state.location.id
            and candidate.alive
        ):
            active_npc = candidate

    return active_npc


def _scene_subjects(
    db: Session,
    state: GameStateSnapshot,
    active_npc: NPC | None,
) -> list[str]:
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
    return [
        *([f"region:{state.region.id}"] if state.region is not None else []),
        *([f"location:{state.location.id}"] if state.location is not None else []),
        *([f"npc:{active_npc.id}"] if active_npc is not None else []),
        *(f"connection:{connection.id}" for connection in outgoing_connections),
        *(f"quest:{quest.id}" for _link, quest in state.active_quests),
    ]


def active_npc_relevant_facts(
    db: Session,
    state: GameStateSnapshot,
    active_interlocutor: str | None,
    player_input: str = "",
) -> list[KnownFact]:
    """Recompute exactly the NPC KNOWLEDGE facts shown to the narrator this turn.

    Lets the engine check, after narration, whether the produced text actually
    voiced one of these facts — without granting the narrator itself any new
    authority. Reuses the same resolution build_context() uses internally so
    the two never drift apart.
    """
    active_npc = _resolve_active_npc(db, state, active_interlocutor)
    if active_npc is None:
        return []
    scene_subjects = _scene_subjects(db, state, active_npc)
    return relevant_known_facts(
        db,
        state.campaign_id,
        KnowerType.NPC,
        active_npc.id,
        scene_subjects=scene_subjects,
        player_input=player_input,
        limit=MAX_CONTEXT_FACTS_PER_KNOWER,
    )


def _proper_nouns(statement: str) -> set[str]:
    """Capitalized words in a fact's statement, i.e. its named entities.

    Skips the sentence's own first word, since it is capitalized purely by
    sentence position ("Uma trilha...", "A Estrada...") regardless of
    whether it is actually a proper noun.
    """
    tokens = list(re.finditer(r"\S+", statement))
    scan_from = tokens[1].start() if len(tokens) > 1 else len(statement)
    return {
        word
        for word in re.findall(r"[A-ZÀ-Ý][\wÀ-ÿ'-]*", statement[scan_from:])
        if len(word) >= 3
    }


def fact_is_revealed_in_text(fact: KnownFact, narrated_text: str) -> bool:
    """Conservative check: every named entity (proper noun) in the fact's
    statement must appear in the narrated text for the fact to count as
    revealed. Paraphrasing of ordinary words ("da região" vs "do") is fine;
    the names themselves are what actually constitute the reveal.

    Deliberately strict (an "all named entities" match) — missing a real
    reveal only means the player can ask again; teaching a fact that was
    not really said would be worse.
    """
    names = _proper_nouns(fact.statement)
    if not names:
        return False
    normalized_text = _normalized(narrated_text)
    return all(
        re.search(rf"\b{re.escape(_normalized(name))}\b", normalized_text)
        for name in names
    )


def build_context(
    db: Session,
    state: GameStateSnapshot,
    active_interlocutor: str | None = None,
    player_input: str = "",
    active_simulated_player: str | None = None,
) -> str:
    """Build minimum scene context while separating truth, perception and knowledge."""
    active_npc = _resolve_active_npc(db, state, active_interlocutor)
    active_transported = next(
        (
            player
            for player in state.nearby_simulated_players
            if player.id == active_simulated_player
            or player.name == active_simulated_player
        ),
        None,
    )
    if (
        active_transported is None
        and active_simulated_player
    ):
        candidate = db.get(
            SimulatedPlayer,
            active_simulated_player,
        )

        if (
            candidate is not None
            and candidate.campaign_id
            == state.campaign_id
            and state.location is not None
            and candidate.location_id
            == state.location.id
            and candidate.status
            == SimulatedPlayerStatus.ACTIVE.value
        ):
            active_transported = candidate

    scene_subjects = _scene_subjects(db, state, active_npc)
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

    transported_relationship = (
        get_character_simulated_player_relationship(
            db,
            state.campaign_id,
            state.character.id,
            active_transported.id,
        )
        if active_transported is not None
        else None
    )

    transported_relationship_guidance = (
        simulated_player_relationship_behavior_guidance(
            transported_relationship
        )
        if transported_relationship is not None
        else ()
    )
    transported_group = (
        active_group_for_player(db, active_transported.id)
        if active_transported is not None
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
        all_player_facts,
    )

    rumored_location_lines = _location_discovery_lines(
        db,
        state,
        {
            DiscoveryStatus.RUMORED,
        },
        all_player_facts,
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
            ]
        )

    perception_lines = [
        "DIRECTLY PERCEPTIBLE LOCATION DETAILS"
    ]

    if state.location is None:
        perception_lines.append("- none")
    else:
        perception_lines.extend(
            [
                f"- {_clip(feature.name, 100)}: "
                f"{_clip(feature.description, 300)}"
                for feature in features
            ]
            or ["- none registered"]
        )

    known_route_lines = [
        "CONNECTED LOCATIONS KNOWN TO PLAYER",
        *(
            _known_connection_lines(
                db,
                state,
                all_player_facts,
            )
            or ["- none"]
        ),
    ]

    visible_lines = ["VISIBLE NPCS"]
    visible_lines.extend(
        [
            (
                f"- {_clip(npc.name, 100)} "
                f"({_clip(npc.role, 120)}; activity={npc.activity})"
            )
            for npc in state.nearby_npcs[:MAX_VISIBLE_ENTITIES]
        ] or ["- none"]
    )
    visible_lines.append("VISIBLE TRANSPORTED PEOPLE")
    visible_lines.extend(
        [
            (
                f"- {_clip(player.name, 100)} "
                f"(Level {player.level}; "
                f"appearance={_clip(player.physical_description or 'unknown', 300)})"
            )
            for player in state.nearby_simulated_players[:MAX_VISIBLE_ENTITIES]
        ]
        or ["- none"]
    )
    encounter_snapshot = build_active_encounter_snapshot(db, state.character.id)
    combat_lines = []
    if encounter_snapshot is not None:
        combat_lines.append("ACTIVE COMBAT PARTICIPANTS")
        combat_lines.extend(
            f"- {_clip(participant.name, 100)} (side={participant.side_key})"
            for participant in encounter_snapshot.participants
        )

    active_npc_visible_now = (
        active_npc is not None
        and any(
            npc.id == active_npc.id
            for npc in state.nearby_npcs
        )
    )

    active_transported_visible_now = (
        active_transported is not None
        and any(
            player.id == active_transported.id
            for player in state.nearby_simulated_players
        )
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
                f"Current activity: {active_npc.activity}",
                (
                    "Conversation status: the NPC remains available in the current scene. "
                    "The conversation may continue naturally."
                    if active_npc_visible_now
                    else (
                        "Conversation status: this NPC participated in the action that just "
                        "occurred but is no longer available in the current scene. "
                        "Narrate the completed interaction, but do not continue the "
                        "conversation afterward."
                    )
                ),
            ]
        )
    active_transported_lines = ["ACTIVE TRANSPORTED PERSON CONTEXT"]
    if active_transported is None:
        active_transported_lines.append("- none")
    else:
        active_transported_lines.extend(
            [
                f"Name: {active_transported.name}",
                (
                    "Location: "
                    f"{state.location.name if state.location else 'unknown'}"
                ),
                (
                    "Visibility: private character context; "
                    "this information is NOT automatically "
                    "known by the protagonist."
                ),
                (
                    "Physical description: "
                    f"{_clip(active_transported.physical_description or 'unknown', 500)}"
                ),
                (
                    "Personality: "
                    f"{_clip(active_transported.personality or 'unknown', 500)}"
                ),
                (
                    "Background: "
                    f"{_clip(active_transported.background or 'unknown', MAX_DESCRIPTION_CHARS)}"
                ),
                (
                    "Current motivation: "
                    f"{_clip(active_transported.motivation or 'unknown', 500)}"
                ),
                (
                    "Current personal goal: "
                    f"{_clip(active_transported.goal or 'unknown', 500)}"
                ),
                (
                    f"Mechanical profile: Level {active_transported.level}; "
                    f"risk tolerance={active_transported.risk_tolerance}; "
                    f"group_id={transported_group.id if transported_group else 'none'}"
                ),
                (
                    "Relationship with player: not registered"
                    if transported_relationship is None
                    else (
                        "Relationship with player: "
                        f"familiarity={transported_relationship.familiarity}, "
                        f"trust={transported_relationship.trust}, "
                        f"affinity={transported_relationship.affinity}"
                    )
                ),
                *(
                    [
                        "Relationship behavior guidance "
                        "(private narrator constraint):",
                        *[
                            f"- {guidance}"
                            for guidance
                            in transported_relationship_guidance
                        ],
                        (
                            "- Relationship values influence behavior but "
                            "never override personality, goals, safety, "
                            "interests, circumstances, or free choice."
                        ),
                    ]
                    if transported_relationship_guidance
                    else []
                ),
                f"Current activity: {active_transported.activity}",
                (
                    "Conversation status: the transported person "
                    "remains available in the current scene. "
                    "The conversation may continue naturally."
                    if active_transported_visible_now
                    else (
                        "Conversation status: this transported person "
                        "participated in the action that just occurred "
                        "but is no longer available in the current scene. "
                        "Narrate the completed interaction, but do not "
                        "continue the conversation afterward."
                    )
                ),
                (
                    "Use personality, background, motivation and goal "
                    "to guide this person's behavior and dialogue. "
                    "Do not reveal private information unless the "
                    "conversation or circumstances justify it."
                ),
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
    inventory_context = build_narrator_inventory_context(
        state.inventory,
        player_input,
    )

    sections = [
        player_section,
        *([inventory_context] if inventory_context else []),
        world_section,
        "\n".join(location_lines),
        "\n".join(perception_lines),
        "\n".join(known_route_lines),
        "\n".join(current_location_knowledge_lines),
        spatial_knowledge_section,
        "\n".join(visible_lines),
        *([("\n".join(combat_lines))] if combat_lines else []),
        "\n".join(active_lines),
        "\n".join(active_transported_lines),
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
    logger.debug("ACTIVE TRANSPORTED PERSON CONTEXT\n%s","\n".join(active_transported_lines),)
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
