import re
from typing import Protocol, Sequence
import unicodedata

from sqlalchemy.orm import Session
from app.db.models.item import ItemInstance
from app.db.models.notice import Notice
from app.db.models.npc import NPC
from app.db.models.organization import Organization, OrganizationMember, OrganizationRole
from app.db.models.quest import CharacterQuestObjective, QuestObjective
from app.db.models.shop import Shop, ShopListing
from app.db.models.simulated_player import SimulatedPlayer
from app.core.enums import (
    CombatActorType,
    DiscoveryStatus,
    KnowerType,
    KnowledgeDocumentType,
    KnowledgeSourceType,
    MemoryOwnerType,
    NoticeStatus,
    OrganizationMembershipStatus,
    OrganizationVisibility,
    ShopStatus,
    SimulatedPlayerStatus,
)
from app.core.logging import get_logger
from app.ai.retrieval.access import knowledge_aware_documents
from app.ai.retrieval.budget import fit_to_budget, format_ranked_documents
from app.ai.retrieval.ranking import rank_documents
from app.ai.retrieval.semantic import ScoredDocument
from app.db.models.knowledge_index import IndexedKnowledgeDocument
from app.db.models.location import (
    CharacterConnectionDiscovery,
    CharacterLocationDiscovery,
    Location,
    LocationConnection,
    LocationFeature,
)
from app.db.models.subregion import Subregion
from app.game.combat.context import build_active_encounter_snapshot
from app.game.game_state import GameStateSnapshot
from app.game.items.context import build_narrator_inventory_context
from app.game.skills.technique_mastery import character_technique_mastery_tier
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
from app.game.organizations.reputation import organization_reputation_category, organization_reputation_score
from app.game.economy.currency import to_denominations
from app.game.economy.local_economy import get_settlement_wealth, gold_circulates_normally
from app.game.economy.pricing import PricingError, resolve_market_price
from app.game.economy.wallet import total_carried_by_owner


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
# Phase 18N — the OPTIONAL retrieved long-term knowledge tail (priority
# level 9); small on purpose relative to the direct-query sections above,
# which stay mandatory and unbounded by this budget.
RETRIEVED_CONTEXT_CHAR_BUDGET = 2000


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


def _quest_objective_lines(db: Session, character_id: str, quest_id: str) -> list[str]:
    """Phase 12L — the same free-text objective descriptions Phase 12G
    already locked down as the entire player-facing surface (no
    trigger_subject_id, no coordinates), now reaching the narrator too."""
    objectives = (
        db.query(QuestObjective)
        .filter(QuestObjective.quest_id == quest_id)
        .order_by(QuestObjective.order)
        .all()
    )
    completed_ids = {
        row.objective_id
        for row in db.query(CharacterQuestObjective).filter(
            CharacterQuestObjective.character_id == character_id,
            CharacterQuestObjective.completed.is_(True),
        )
    }
    return [
        f"    - {_clip(objective.description, 200)} "
        f"[{'completed' if objective.id in completed_ids else 'pending'}]"
        + (" (optional)" if objective.optional else "")
        for objective in objectives
    ]


def _organization_leader_title(db: Session, organization_id: str) -> str | None:
    row = (
        db.query(OrganizationMember, OrganizationRole)
        .join(OrganizationRole, OrganizationMember.role_id == OrganizationRole.id)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
        .order_by(OrganizationRole.rank_order)
        .first()
    )
    return row[1].title if row else None


def _known_organizations_lines(db: Session, character) -> list[str]:
    """Phase 13N — visibility-gated the same way Phase 11L gated known
    techniques: only organizations the character is actually a member of,
    or PUBLIC ones headquartered right where the character currently is
    (a visible local presence — "visible symbols", per the spec's
    NARRATOR RULES), are shown at all. PRIVATE/SECRET organizations never
    appear here just because they exist in the campaign."""
    member_org_ids = {
        member.organization_id
        for member in db.query(OrganizationMember).filter(
            OrganizationMember.member_type == CombatActorType.CHARACTER,
            OrganizationMember.member_id == character.id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
    }
    local_public = (
        db.query(Organization)
        .filter(
            Organization.visibility == OrganizationVisibility.PUBLIC,
            Organization.headquarters_location_id == character.location_id,
        )
        .all()
        if character.location_id
        else []
    )
    organizations = {
        organization.id: organization
        for organization in (
            [db.get(Organization, org_id) for org_id in member_org_ids] + local_public
        )
        if organization is not None
    }

    lines = ["KNOWN ORGANIZATIONS"]
    for organization in organizations.values():
        member_row = (
            db.query(OrganizationMember)
            .filter(
                OrganizationMember.organization_id == organization.id,
                OrganizationMember.member_type == CombatActorType.CHARACTER,
                OrganizationMember.member_id == character.id,
                OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
            )
            .first()
        )
        membership_text = "Not a member"
        if member_row is not None:
            role = db.get(OrganizationRole, member_row.role_id) if member_row.role_id else None
            membership_text = f"Member ({role.title})" if role else "Member"

        leader_title = _organization_leader_title(db, organization.id)
        score = organization_reputation_score(
            db, organization.id, CombatActorType.CHARACTER, character.id
        )
        reputation = organization_reputation_category(score)
        notice_count = (
            db.query(Notice)
            .filter(
                Notice.author_organization_id == organization.id,
                Notice.status == NoticeStatus.ACTIVE,
            )
            .count()
        )

        lines.append(
            f"- {organization.name} [{organization.organization_type}] — "
            f"headquarters: {'known' if organization.headquarters_location_id else 'unknown'}; "
            f"leader: {leader_title or 'unknown'}; "
            f"reputation with this character: {reputation}; "
            f"membership: {membership_text}; known notices: {notice_count}"
        )
    if len(lines) == 1:
        lines.append("- none")
    lines.append(
        "Only state organization facts explicitly listed above. Never invent secret "
        "goals, hidden treasury, hidden membership, alliances, wars, or reputation "
        "changes the character has no way of knowing."
    )
    return lines


def _currency_context_lines(db: Session, character) -> list[str]:
    """Phase 14N — the character's own carried money, in denominations
    (Phase 14A's own preferred display), always safe to show since it is
    the character's own wallet, never anyone else's."""
    total_bronze = total_carried_by_owner(db, CombatActorType.CHARACTER, character.id)
    breakdown = to_denominations(total_bronze)
    return [
        "CURRENCY",
        f"Gold: {breakdown.gold}",
        f"Silver: {breakdown.silver}",
        f"Bronze: {breakdown.bronze}",
        "This is exactly what the character carries. Never invent additional money, "
        "change a balance, or complete a purchase/payment — only the backend does that.",
    ]


_BIOME_TEXTURE = {
    "PLAINS": "planícies abertas",
    "FOREST": "floresta densa",
    "HILLS": "colinas",
    "MOUNTAINS": "terreno montanhoso",
    "WETLANDS": "pântano",
    "RIVER_VALLEY": "vale fluvial",
    "LAKE_COUNTRY": "terras lacustres",
    "COASTAL": "litoral",
    "FRONTIER": "fronteira pouco povoada",
}

_DANGER_TEXTURE = {
    "SAFE": "geralmente segura",
    "LOW": "razoavelmente segura",
    "MODERATE": "moderadamente perigosa",
    "HIGH": "perigosa",
    "SEVERE": "extremamente perigosa",
}


def _regional_context_lines(db: Session, character) -> list[str]:
    """Phase 15S — massive-region texture for wherever the character
    currently physically is (never the Region's other subregions/
    settlements — Do NOT send the entire massive Region to the LLM,
    spec). Only category/adjective-level facts (biome, danger), same
    trust level as Phase 14N's wealth band line — never the subregion's
    proper name, which has no Knowledge-gating mechanism of its own yet."""
    if character.location_id is None:
        return []
    location = db.get(Location, character.location_id)
    if location is None or location.subregion_id is None:
        return []
    subregion = db.get(Subregion, location.subregion_id)
    if subregion is None:
        return []
    biome_text = _BIOME_TEXTURE.get(str(subregion.biome), "terreno variado")
    danger_text = _DANGER_TEXTURE.get(str(subregion.danger_level), "de perigo incerto")
    return [
        "REGIONAL CONTEXT",
        f"This area is characterized by {biome_text}, generally considered {danger_text}.",
    ]


def _local_economy_context_lines(db: Session, character) -> list[str]:
    """Phase 14N — settlement wealth (Phase 14I) is a narrative texture
    hint, never a price. Money communicates world stakes: this line lets
    the narrator phrase Gold as unusual where it should be, without
    inventing that judgment itself."""
    if character.location_id is None:
        return []
    wealth_band = get_settlement_wealth(db, character.location_id)
    gold_is_routine = gold_circulates_normally(wealth_band)
    return [
        "LOCAL ECONOMY",
        f"Settlement wealth: {wealth_band}",
        "Gold coins circulate routinely here."
        if gold_is_routine
        else "Gold is unusual here — even a single Gold coin may draw attention, "
        "suspicion, or curiosity; small shops may lack change for it.",
    ]


def _nearby_shops_context_lines(db: Session, character) -> list[str]:
    """Phase 14N — only shops physically here (Phase 14G never assumed a
    global storefront menu), with only what a browsing customer would
    actually see: name, whether it's open, and priced stock. Never the
    shop's till or specialization internals."""
    lines = ["NEARBY SHOPS"]
    if character.location_id is None:
        lines.append("- none")
        return lines
    shops = (
        db.query(Shop)
        .filter(Shop.location_id == character.location_id)
        .order_by(Shop.name)
        .limit(MAX_VISIBLE_ENTITIES)
        .all()
    )
    if not shops:
        lines.append("- none")
        return lines
    for shop in shops:
        status_text = "open" if shop.status == ShopStatus.OPEN else "closed"
        lines.append(f"- {shop.name} [{status_text}]")
        if shop.status != ShopStatus.OPEN:
            continue
        listings = (
            db.query(ShopListing)
            .join(ItemInstance, ItemInstance.id == ShopListing.item_instance_id)
            .filter(ShopListing.shop_id == shop.id)
            .limit(MAX_VISIBLE_ENTITIES)
            .all()
        )
        for listing in listings:
            item = db.get(ItemInstance, listing.item_instance_id)
            if item is None:
                continue
            if listing.asking_price_bronze is not None:
                price = listing.asking_price_bronze
            else:
                try:
                    price = resolve_market_price(db, item)
                except PricingError:
                    continue
            lines.append(f"    - {item.definition.name}: {price} bronze")
    lines.append(
        "Only these listed items and prices are for sale. Never invent stock, a price, "
        "or complete a transaction — the backend already decides all of that."
    )
    return lines


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
        # Phase 17P — closes a real gap the Phase 15 REGIONAL CONTEXT
        # section itself flagged (_regional_context_lines below: "the
        # subregion's proper name... has no Knowledge-gating mechanism
        # of its own yet"). Subregion-level geographic aspect facts
        # (17A/17J — existence, dangers, description...) now surface in
        # KNOWN/RUMORED FACTS the same way region/location facts already
        # do, with zero other change to this module: relevant_known_facts
        # already matches by subject alone.
        *(
            [f"subregion:{state.location.subregion_id}"]
            if state.location is not None and state.location.subregion_id is not None
            else []
        ),
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


_RETRIEVED_LONG_TERM_DOCUMENT_TYPES = [
    KnowledgeDocumentType.IMPORTANT_HISTORY,
    KnowledgeDocumentType.RELATIONSHIP,
]

# Phase 18O — "current location lore" (the spec's own tavern-revisit
# example: identity, current state, and any established history for
# exactly the location the character is standing in).
_LOCATION_LORE_DOCUMENT_TYPES = [
    KnowledgeDocumentType.IDENTITY,
    KnowledgeDocumentType.BACKGROUND,
    KnowledgeDocumentType.CURRENT_STATE,
]


def _current_location_lore_candidates(
    db: Session, state: GameStateSnapshot
) -> list[IndexedKnowledgeDocument]:
    """Only the location the character currently occupies — never every
    location ever discovered. Still gated by knowledge_aware_documents
    (Phase 18I/18G): a canon document existing for this location never
    implies the player may see it."""
    if state.location is None:
        return []
    candidates = knowledge_aware_documents(
        db, state.campaign_id, KnowerType.PLAYER, state.character.id,
        source_types=[KnowledgeSourceType.LOCATION],
        document_types=_LOCATION_LORE_DOCUMENT_TYPES,
    )
    return [document for document in candidates if document.source_id == state.location.id]


def _retrieved_long_term_context(
    db: Session,
    state: GameStateSnapshot,
    active_npc: NPC | None,
    scene_subjects: Sequence[str],
) -> str:
    """Phase 18N/18O — Context Builder Integration + Narrator Retrieval.

    The OPTIONAL retrieved tail (priority level 9: relevant long-term
    history) appended AFTER the existing direct-query NPC/PLAYER memory
    sections above — this never replaces them, per the spec's explicit
    "do not replace the Context Builder with RAG". Every candidate comes
    from knowledge_aware_documents (Phase 18I), so nothing a knower
    lacks access to can appear here regardless of how it ranks.

    Narrator retrieval (Phase 18O) is not a separate pipeline: the
    Narrator is currently the sole consumer of build_context's output
    (app.game.engine passes it straight to narrator.narrate), so this
    same section already serves it — continuity via relationship/
    history documents (Phase 18N) plus current-location lore (this
    subphase) for the tavern-revisit style case. narrator.py itself
    still cannot see the database (architecture-enforced); it only ever
    receives this already-built, already-filtered string.

    No LLMService is threaded through build_context — that would be a
    much larger, separate integration than this subphase's scope — so
    the semantic-similarity component of ranking (Phase 18H) stays
    neutral (0.0) here; entity-match/recency/importance (Phase 18K)
    still meaningfully order the result.

    Ranked per-knower (player, then the active NPC) before merging: a
    single hard-filter pass in app.ai.retrieval.ranking.rank_documents
    only ever checks one knower at a time, so combining two knowers'
    candidates before ranking would incorrectly drop the NPC's own
    accessible documents against the player's access rules.
    """
    current_world_minute = state.world_time.total_minutes()

    def _ranked(candidates: list, knower_type: KnowerType, knower_id: str):
        return rank_documents(
            db, state.campaign_id,
            [ScoredDocument(document, 0.0) for document in candidates],
            knower_type, knower_id,
            current_world_minute=current_world_minute,
            scene_subjects=scene_subjects,
            query_description="Context Builder: retrieved long-term knowledge (18N/18O)",
        )

    def _ranked_for(knower_type: KnowerType, knower_id: str):
        candidates = knowledge_aware_documents(
            db, state.campaign_id, knower_type, knower_id,
            document_types=_RETRIEVED_LONG_TERM_DOCUMENT_TYPES,
        )
        return _ranked(candidates, knower_type, knower_id)

    merged = _ranked_for(KnowerType.PLAYER, state.character.id)
    merged += _ranked(
        _current_location_lore_candidates(db, state), KnowerType.PLAYER, state.character.id
    )
    if active_npc is not None:
        merged = merged + _ranked_for(KnowerType.NPC, active_npc.id)
    merged.sort(key=lambda ranked: ranked.score, reverse=True)

    budgeted = fit_to_budget(merged, max_chars=RETRIEVED_CONTEXT_CHAR_BUDGET)
    if not budgeted.included:
        return "RELEVANT LONG-TERM KNOWLEDGE\n- none recalled"
    return format_ranked_documents(budgeted.included)


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
    technique_lines = ["KNOWN TECHNIQUES"]
    technique_lines.extend(
        [
            f"- {technique.name} [{technique.technique_type}, mastery: "
            f"{character_technique_mastery_tier(db, state.character.id, technique.id).value}]"
            for technique in state.techniques
        ]
        or ["- none learned yet"]
    )
    technique_lines.append(
        "Mastery is a qualitative reliability tier only. Never invent damage, "
        "cooldowns, success chances or other numeric effects from a technique "
        "or its mastery."
    )
    quest_lines = ["ACTIVE QUESTS"]
    for link, quest in state.active_quests[:MAX_ACTIVE_QUESTS]:
        quest_lines.append(f"- {_clip(quest.name, 160)} [{link.status}]")
        quest_lines.extend(_quest_objective_lines(db, state.character.id, quest.id))
    if not state.active_quests:
        quest_lines.append("- none")
    quest_lines.append(
        "Objective text is exactly what the character currently knows. Never state a "
        "location, identity, or detail beyond it — no magic waypoints or hidden facts."
    )
    organization_lines = _known_organizations_lines(db, state.character)
    currency_lines = _currency_context_lines(db, state.character)
    regional_lines = _regional_context_lines(db, state.character)
    local_economy_lines = _local_economy_context_lines(db, state.character)
    shop_lines = _nearby_shops_context_lines(db, state.character)
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
        "\n".join(organization_lines),
        "\n".join(currency_lines),
        *([("\n".join(regional_lines))] if regional_lines else []),
        *([("\n".join(local_economy_lines))] if local_economy_lines else []),
        "\n".join(shop_lines),
        npc_knowledge_section,
        player_knowledge_section,
        npc_memory_section,
        player_memory_section,
        _retrieved_long_term_context(db, state, active_npc, scene_subjects),
        "\n".join(input_canon_lines),
        "\n".join(quest_lines),
        "\n".join(technique_lines),
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
