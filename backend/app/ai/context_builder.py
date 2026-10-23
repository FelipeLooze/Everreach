import re
from dataclasses import dataclass, replace
from typing import Protocol, Sequence
import unicodedata

from sqlalchemy.orm import Session
from app.ai.conversational_act import (
    ConversationalSubject,
    classify_subject,
    is_existence_question,
    is_price_question,
    economic_service_asked_about,
    service_type_asked_about,
)
from app.db.models.item import ItemInstance
from app.db.models.notice import Notice
from app.db.models.npc import NPC
from app.game.world.content_pools import SETTLEMENT_SERVICE_POOL
from app.db.models.organization import OrganizationMember, OrganizationRole
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
    ShopStatus,
    SimulatedPlayerStatus,
    connection_type_label_pt,
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
from app.game.players.arrival_kit import TRANSPORTED_OUTFIT_APPEARANCE, transported_appearance
from app.game.npcs.service import (
    KnownFact,
    effective_npc_location_id,
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
from app.game.organizations.visibility import visible_organizations_for_character
from app.ai.people_present import npc_appearance_pt
from app.game.players.appearance import ensure_transported_features
from app.game.schedules import (
    job_hours_text,
    player_knows_job_schedule,
    player_knows_quest_schedule,
)
from app.game.economy.currency import to_denominations
from app.game.economy.local_economy import get_settlement_wealth, gold_circulates_normally
from app.game.economy.pricing import PricingError
from app.game.economy.supply_demand import resolve_local_market_price
from app.game.economy.economic_canon import current_price, get_service_value
from app.game.economy.wallet import total_carried_by_owner


logger = get_logger("context")

RECENT_HISTORY_ENTRIES = 6
MAX_HISTORY_ENTRY_CHARS = 1500
MAX_CONTEXT_FACTS_PER_KNOWER = 12
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


@dataclass(frozen=True)
class NarrativeContext:
    """Phase 24C — the same information build_context() has always
    assembled, now named and structured instead of anonymous strings
    joined inline. Every field here is exactly one of the pre-existing
    section strings build_context already computed — this is
    deliberately NOT a rewrite of what's gathered or how knowledge
    filtering works, only a seam so a future consumer (a relevance
    check, a token-budget trimmer) can address "the NPC knowledge
    section" by name instead of re-parsing the final joined string.

    serialize() reproduces build_context()'s exact historical section
    order and exact conditional-inclusion rules (only inventory/
    combat/regional/local_economy are ever omitted, when empty; every
    other section is always present even when its own content is just
    a header) — this changes nothing about what the narrator receives
    today. Phase 24M (context priority & token budgeting) is where
    that ordering itself becomes a deliberate, tunable policy instead
    of a fixed sequence.
    """

    player: str
    inventory: str
    world: str
    location: str
    perception: str
    known_routes: str
    current_location_knowledge: str
    spatial_knowledge: str
    visible_npcs: str
    combat: str
    active_npc: str
    active_transported: str
    direct_question_grounding: str
    organizations: str
    currency: str
    regional: str
    local_economy: str
    shops: str
    npc_knowledge: str
    player_knowledge: str
    npc_memories: str
    player_memories: str
    retrieved_long_term: str
    input_canon_check: str
    quests: str
    techniques: str
    canon_rule: str

    def as_sections(self) -> list[str]:
        return [
            self.player,
            *([self.inventory] if self.inventory else []),
            self.world,
            self.location,
            self.perception,
            self.known_routes,
            self.current_location_knowledge,
            self.spatial_knowledge,
            self.visible_npcs,
            *([self.combat] if self.combat else []),
            self.active_npc,
            self.active_transported,
            *([self.direct_question_grounding] if self.direct_question_grounding else []),
            self.organizations,
            self.currency,
            *([self.regional] if self.regional else []),
            *([self.local_economy] if self.local_economy else []),
            self.shops,
            self.npc_knowledge,
            self.player_knowledge,
            self.npc_memories,
            self.player_memories,
            self.retrieved_long_term,
            self.input_canon_check,
            self.quests,
            self.techniques,
            self.canon_rule,
        ]

    def serialize(self) -> str:
        return "\n\n".join(self.as_sections())


# Phase 24M — Context Priority & Token Budgeting. Distinct from every
# existing per-field clip above (MAX_DESCRIPTION_CHARS,
# MAX_CONTEXT_FACTS_PER_KNOWER, RETRIEVED_CONTEXT_CHAR_BUDGET, ...) and
# from Phase 18L's own retrieval-tail budget (app.ai.retrieval.budget,
# which already bounds priority tier 9 on its own before it ever reaches
# NarrativeContext.retrieved_long_term) — this is the one GLOBAL ceiling
# on context_builder's own combined output, matching the master plan's
# own observation: "The current system only clips individual fields and
# RAG." No real tokenizer is wired in here; chars/4 is the same rough,
# standard estimate used industry-wide when an exact tokenizer isn't
# available, tracked for observability only (spec's "track estimated
# prompt size/tokens"), never used as the actual trim unit (chars are).
#
# Mandatory/high-priority sections — player identity, active NPC, NPC
# knowledge, current location/scene, canon rule, the player-input canon
# audit — are NEVER dropped by this budget; only the spec's own lowest-
# priority tiers (9: long-term retrieval; 10: decorative/background) are
# ever sacrificed, lowest first, same "never a shuffle" invariant Phase
# 18L's own budget already established (a field is either kept whole or
# dropped whole, never partially re-truncated by this mechanism — it
# already arrived pre-clipped by its own field-level budget). "Never
# sacrifice the current player turn to preserve stale history" (spec) is
# respected by construction: this budget never touches narrator.py's own
# current-turn block or recent-history parameter at all — neither is
# part of what context_builder produces.
MAX_CONTEXT_BUDGET_CHARS = 20000
_CHARS_PER_TOKEN_ESTIMATE = 4


def _estimated_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN_ESTIMATE


@dataclass(frozen=True)
class ContextBudgetResult:
    context: NarrativeContext
    used_chars: int
    dropped_sections: tuple[str, ...]


# Lowest priority first — the ONLY fields this budget is ever allowed to
# drop, in the exact order they're sacrificed.
_DROPPABLE_FIELDS_LOWEST_PRIORITY_FIRST = (
    "retrieved_long_term",
    "regional",
    "local_economy",
    "shops",
    "player_knowledge",
    "player_memories",
    "npc_memories",
)


def apply_context_budget(
    ctx: NarrativeContext, *, budget_chars: int = MAX_CONTEXT_BUDGET_CHARS
) -> ContextBudgetResult:
    original_chars = len(ctx.serialize())
    if original_chars <= budget_chars:
        return ContextBudgetResult(context=ctx, used_chars=original_chars, dropped_sections=())

    dropped: list[str] = []
    used_chars = original_chars
    for field_name in _DROPPABLE_FIELDS_LOWEST_PRIORITY_FIRST:
        if getattr(ctx, field_name):
            ctx = replace(ctx, **{field_name: ""})
            dropped.append(field_name)
            used_chars = len(ctx.serialize())
            if used_chars <= budget_chars:
                break

    logger.warning(
        "Context exceeded budget (%s chars, ~%s tokens, > %s char limit); dropped lowest-"
        "priority sections: %s; now %s chars (~%s tokens)",
        original_chars,
        original_chars // _CHARS_PER_TOKEN_ESTIMATE,
        budget_chars,
        dropped or "(none droppable)",
        used_chars,
        used_chars // _CHARS_PER_TOKEN_ESTIMATE,
    )
    return ContextBudgetResult(context=ctx, used_chars=used_chars, dropped_sections=tuple(dropped))


def _clip(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def _format_known_fact(fact: KnownFact) -> str:
    statement = _clip(fact.statement, MAX_FACT_CHARS)
    source = _clip(fact.source, 80)
    return f"- [{fact.certainty}; fonte: {source}] {statement}"


def _format_known_fact_without_certainty(fact: KnownFact) -> str:
    statement = _clip(fact.statement, MAX_FACT_CHARS)
    source = _clip(fact.source, 80)
    return f"- [fonte: {source}] {statement}"


# Phase 24F — certainty tiers already exist deep in the Phase 12-era
# knowledge/rumor infrastructure (app.game.knowledge.rumors/geography,
# KnowledgeCertainty); this only changes how they reach the narrator for
# the active NPC's own knowledge, grouping by tier instead of an inline
# per-line tag, so a rumor the NPC only heard secondhand can't be skimmed
# as equally solid as a confirmed fact.
_CERTAINTY_GROUP_ORDER = (
    ("CONFIRMED", "CONFIRMED FACTS (the NPC treats these as certain)"),
    ("BELIEVED", "BELIEVED (the NPC thinks this is likely true, but is not certain)"),
    ("RUMOR", "RUMORS (the NPC only heard this secondhand; it may be wrong)"),
)


def _grouped_npc_knowledge_lines(facts: list[KnownFact]) -> list[str]:
    if not facts:
        return ["- none supplied"]
    by_tier: dict[str, list[KnownFact]] = {}
    for fact in facts:
        by_tier.setdefault(fact.certainty, []).append(fact)
    lines: list[str] = []
    for tier_value, heading in _CERTAINTY_GROUP_ORDER:
        tier_facts = by_tier.pop(tier_value, [])
        if not tier_facts:
            continue
        lines.append(heading)
        lines.extend(_format_known_fact_without_certainty(fact) for fact in tier_facts)
    # Any certainty value outside the three known tiers is future-proofing
    # only (KnowledgeCertainty is the sole writer today) — still surfaced
    # rather than silently dropped.
    for tier_value, tier_facts in by_tier.items():
        lines.append(tier_value)
        lines.extend(_format_known_fact_without_certainty(fact) for fact in tier_facts)
    return lines


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


def _first_meeting_note(db: Session, character, npc) -> str:
    """Playtest: the innkeeper greeted a first-time visitor with "Volta
    rápido", as if he were a regular. Say so when they have never met."""
    from app.db.models.relationship import CharacterNPCRelationship

    met = db.query(CharacterNPCRelationship.id).filter(
        CharacterNPCRelationship.character_id == character.id,
        CharacterNPCRelationship.npc_id == npc.id,
    ).first()
    if met is not None:
        return ""
    return "; has NEVER met the character — treats them as a stranger, never as someone known or returning"


def _transported_label(db: Session, character, player) -> str:
    """The name only once the character has met this person. Playtests kept
    showing transported strangers called by name in narration, because the
    name sat right here in the context."""
    from app.game.groups.companions import _has_met

    if _has_met(db, character.campaign_id, character, player):
        return _clip(player.name, 100)
    return (
        "[a stranger whose name the character does not know — never name them; "
        "describe them by appearance]"
    )


def _gender_note(name: str) -> str:
    from app.game.world.generator import gender_for_name

    return {"F": "; gender=female", "M": "; gender=male"}.get(gender_for_name(name), "")


def _guild_progress_text(db: Session, organization, known_ids: set[str], *, member: bool) -> str:
    """Members know their guild's shared goal; anyone who knows two
    organizations may know how they stand with each other."""
    from app.game.organizations import guild_goals
    from app.game.organizations.player_guilds import known_relations

    text = ""
    goal = guild_goals.current_goal(db, organization) if member else None
    if goal is not None and goal.target:
        text += f"; shared goal: {goal.description} ({goal.progress}/{goal.target})"
    relations = known_relations(db, organization, known_ids)
    if relations:
        text += "; relations: " + ", ".join(f"{relation_type} with {other.name}" for other, relation_type in relations)
    return text


def _transported_guild_line(db: Session, simulated_player_id: str) -> str:
    """The guild a transported person belongs to — they talk about it freely;
    talking with them is how the player learns it exists."""
    from app.game.organizations.player_guilds import transported_guild_of

    guild = transported_guild_of(db, CombatActorType.SIMULATED_PLAYER, simulated_player_id)
    if guild is None:
        return "Guild: none"
    standing = "registered" if guild.formality == "FORMALLY_RECOGNIZED" else "informal"
    return f'Guild: member of "{guild.name}" ({guild.focus or "GUILD"}, {standing}, founded by transported people)'


def _travel_companion_lines(db: Session, character_id: str) -> list[str]:
    """Transported people who accepted to travel with the protagonist."""
    from app.db.models.character import Character
    from app.game.groups.companions import companions_of

    character = db.get(Character, character_id)
    companions = companions_of(db, character) if character is not None else []
    if not companions:
        return []
    names = ", ".join(companion.name for companion in companions)
    return [f"Travel companions (accepted to travel with the protagonist and move with them): {names}"]


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
    techniques. Membership, a public local presence, or participation in
    one of the organization's real contracts can establish knowledge.
    PRIVATE/SECRET organizations never appear merely because they exist
    in the campaign. The same boundary powers the player-facing Social
    panel, preventing the UI and narrator from disagreeing."""
    organizations = visible_organizations_for_character(db, character)

    lines = ["KNOWN ORGANIZATIONS"]
    known_ids = {organization.id for organization in organizations}
    for organization in organizations:
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

        standing = (
            "registered with a native authority"
            if organization.formality == "FORMALLY_RECOGNIZED"
            else "informal, not registered"
        )
        origin = (
            f"founded by transported people ({organization.focus or 'GUILD'}), {standing}"
            if organization.origin == "TRANSPORTED_CREATED"
            else "native institution"
        )
        lines.append(
            f"- {organization.name} [{organization.organization_type}; {origin}] — "
            f"headquarters: {'known' if organization.headquarters_location_id else 'unknown'}; "
            f"leader: {leader_title or 'unknown'}; "
            f"reputation with this character: {reputation}; "
            f"membership: {membership_text}; known notices: {notice_count}"
            + _guild_progress_text(db, organization, known_ids, member=member_row is not None)
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


def _quest_schedule_note(db: Session, character, quest) -> str:
    if not quest.schedule_text:
        return ""
    if player_knows_quest_schedule(db, character.campaign_id, character.id, quest):
        return f" — when: {quest.schedule_text}"
    return " — when: unknown to the character; never state a time for it"


def _settlement_jobs_context_lines(db: Session, character) -> list[str]:
    """Openings posted in this settlement (the public board lists them, so
    any local may mention them), with their real pay and shift length.
    Playtest: asked about work, the elder and then the blacksmith promised
    "a meal and a corner to sleep, bronze if the week was good" for a job
    that pays a fixed 12 Bronze a shift — nothing told them the terms."""
    from app.core.enums import JobApplicationStatus, JobStatus
    from app.db.models.job import Job, JobApplication

    if character.location_id is None:
        return []
    here = db.get(Location, character.location_id)
    settlement = here
    while settlement is not None and settlement.parent_location_id:
        settlement = db.get(Location, settlement.parent_location_id)
    if settlement is None:
        return []
    place_ids = {settlement.id} | {
        location_id
        for (location_id,) in db.query(Location.id).filter(Location.parent_location_id == settlement.id)
    }
    jobs = (
        db.query(Job)
        .filter(Job.campaign_id == character.campaign_id, Job.location_id.in_(place_ids))
        .order_by(Job.id)
        .all()
    )
    lines = ["WORK IN THIS SETTLEMENT"]
    for job in jobs:
        application = (
            db.query(JobApplication)
            .filter(
                JobApplication.job_id == job.id,
                JobApplication.applicant_type == CombatActorType.CHARACTER.value,
                JobApplication.applicant_id == character.id,
                JobApplication.status == JobApplicationStatus.ACTIVE.value,
            )
            .first()
        )
        if application is None and job.status != JobStatus.OPEN.value:
            continue
        workplace = db.get(Location, job.location_id)
        standing = "the character already holds this job" if application else "open"
        hours, minutes = divmod(job.work_minutes, 60)
        shift = f"{hours}h{minutes:02d}" if minutes else f"{hours}h"
        if job_hours_text(job) is None:
            when = "shifts at any time"
        elif player_knows_job_schedule(db, character.campaign_id, character.id, job):
            when = f"shifts {job_hours_text(job)}"
        else:
            when = "shift hours unknown to the character (the employer knows them)"
        lines.append(
            f"- {job.title} at {workplace.name if workplace else 'unknown'} [{standing}]: "
            f"{job.wage_bronze} bronze per shift of {shift}; {when}. {job.description}"
        )
    if len(lines) == 1:
        lines.append("- none")
    lines.append(
        "These are the only paid jobs here and their exact terms. Never promise meals, lodging, "
        "other pay or other openings, and never hire the character in narration — "
        "the backend does that when the character takes the job. A shift may start at any "
        "moment inside its hours, right now included: never say work starts tomorrow, at dawn "
        "or at any other time those hours don't say."
    )
    return lines


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
        operator_available = True
        if shop.operator_type == CombatActorType.NPC.value:
            operator = db.get(NPC, shop.operator_id)
            operator_available = bool(
                operator
                and operator.alive
                and not operator.incapacitated
                and effective_npc_location_id(operator) == shop.location_id
            )
        status_text = (
            "open"
            if shop.status == ShopStatus.OPEN and operator_available
            else "unattended"
            if shop.status == ShopStatus.OPEN
            else "closed"
        )
        lines.append(f"- {shop.name} [{status_text}]")
        if shop.status != ShopStatus.OPEN or not operator_available:
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
                    price = resolve_local_market_price(db, item, shop.location_id)
                except PricingError:
                    continue
            quantity = f" ({item.quantity} em estoque)" if item.quantity > 1 else ""
            lines.append(f"    - {item.definition.name}: {price} bronze por unidade{quantity}")
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


# Phase 24J.4 — Issue 1 (Relational Geography Hallucination). Confirmed
# via live trace: an early-game question ("existe uma estalagem?") gets
# asked before the player has been TAUGHT any destination's proper NAME —
# every entry in CONNECTED LOCATIONS KNOWN TO PLAYER redacts to "Local
# desconhecido", leaving narrator._find_relational_geography_violations
# with zero ground truth to correlate a claim against, even though the
# STRUCTURAL fact (this destination is a service of type X) is fully
# known and not secret at all — the existing CANONICAL LOCATION CONTEXT
# block already treats a location's Type as "DIRECTLY PERCEPTIBLE" even
# when its Name is hidden; this line was the one place that distinction
# wasn't carried through. Exposing the type label lets the validator
# still correlate a claim like "a estalagem fica a leste" to its real
# connection via the generic service alias, even before the proper noun
# is known.
_LOCATION_TYPE_LABELS_PT = {
    location_type: name for name, location_type, _description in SETTLEMENT_SERVICE_POOL.values()
}


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
        # Type stays visible even when the proper noun is redacted above —
        # see this function's own Phase 24J.4 docstring note. Square
        # brackets (not parens) so it can't be confused with the
        # route-kind parenthetical that always follows.
        type_label = _LOCATION_TYPE_LABELS_PT.get(destination.type)
        destination_label = (
            f"{destination_name} [{type_label}]" if type_label else destination_name
        )

        # Phase 24J.4 — this line is the ONLY structured, per-destination
        # connection fact the narrator/validator has access to; it must
        # speak the same Portuguese vocabulary the model actually narrates
        # in (24J.2 already fixed this for perception.service's own route
        # sentences, but this separate representation still leaked the raw
        # English enum value, e.g. "PATH").
        lines.append(
            f"- {direction} -> {destination_label} "
            f"({connection_type_label_pt(connection.connection_type)}, distância {connection.distance:g})"
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


def _npc_is_present_at(npc: NPC | None, location_id: str | None) -> bool:
    """Simplification Pass S1.2/S1.3 — is this NPC ACTUALLY here, using
    the same effective-location rule app.game.npcs.service.npcs_at_
    location's SQL expression encodes (WORKING + a set workplace
    resolves there; everything else is the NPC's ordinary location_id).
    Every DIRECT QUESTION GROUNDING branch's own "is this NPC a local
    resident who'd know this" check needs this, not raw location_id —
    S1.2 made a WORKING NPC's real presence diverge from their base
    location_id, and this context (an NPC actually being talked to at
    their own workplace) is now the common case, not an edge case."""
    if npc is None or location_id is None:
        return False
    return effective_npc_location_id(npc) == location_id


def _direct_question_grounding_lines(
    db: Session,
    player_input: str,
    state: GameStateSnapshot,
    active_npc: NPC | None,
    location_name_known: bool,
) -> list[str]:
    """Phase 24J.1 Step 4 — for a direct question about the active NPC's
    own identity or the current settlement's name, tell the narrator
    up front what it is actually authorized to say, instead of relying
    only on after-the-fact repair. Deliberately tiny and only fires for
    the two subjects with an unambiguous, data-driven answer (mirrors
    the same acceptance signals app.ai.validation.relevance now checks)
    — never a general-purpose answer key, and never a substitute for the
    exact player utterance staying authoritative elsewhere.
    """
    subject = classify_subject(player_input)

    if subject == ConversationalSubject.SELF_NAME:
        if active_npc is None:
            return []
        return [
            "DIRECT QUESTION GROUNDING",
            "The player is asking the ACTIVE interlocutor's own name/identity.",
            f"Authorized answer: {active_npc.name}",
        ]

    if subject in (ConversationalSubject.CURRENT_SETTLEMENT, ConversationalSubject.CURRENT_LOCATION):
        if state.location is None or location_name_known:
            return []
        is_local_resident = _npc_is_present_at(active_npc, state.location.id)
        if is_local_resident:
            # "Authorized answer:" stays on its own line with ONLY the bare
            # fact — this exact line is re-parsed verbatim by narrator.py's
            # _direct_question_grounding_fact and may be used as-is in
            # player-facing repair/fallback text (Steps 6/7), so it must
            # never carry the explanatory clause below.
            return [
                "DIRECT QUESTION GROUNDING",
                "The player is asking for the CURRENT location/settlement's name.",
                f"Authorized answer: {state.location.name}",
                "The active interlocutor lives or works here and may state it plainly; this "
                "is ordinary local knowledge, not a secret.",
            ]
        return [
            "DIRECT QUESTION GROUNDING",
            "The player is asking for the CURRENT location/settlement's name.",
            "No confirmed answer available — nothing establishes the active interlocutor (if "
            "any) as someone who would know this name. A genuine admission of not knowing, or "
            "a refusal, is the correct response here. Never invent or guess the name.",
        ]

    # Phase 24J.4 — Issue 2 (False Factual Denial). Confirmed live: a
    # resident NPC confidently denied a service that demonstrably exists
    # one hop away. Steering this up front (like the two branches above)
    # is cheaper and more reliable than only catching it after the fact —
    # this line is re-parsed verbatim by the SAME
    # _direct_question_grounding_fact narrator.py already uses for the
    # other two subjects, so the targeted-repair safety net (Issue 2's
    # validator, app.ai.validation.existence) reuses this exact fact too.
    if subject == ConversationalSubject.SERVICE and is_existence_question(player_input):
        service_type = service_type_asked_about(player_input)
        if service_type is not None and state.location is not None:
            service_location = (
                db.query(Location)
                .join(LocationConnection, LocationConnection.to_location_id == Location.id)
                .filter(
                    LocationConnection.from_location_id == state.location.id,
                    LocationConnection.active.is_(True),
                    Location.type == service_type,
                )
                .first()
            )
            is_local_resident = _npc_is_present_at(active_npc, state.location.id)
            if service_location is not None and is_local_resident:
                return [
                    "DIRECT QUESTION GROUNDING",
                    "The player is asking whether a specific local service exists.",
                    f"Authorized answer: sim, {service_location.name} existe e é conhecida "
                    "localmente.",
                    "The active interlocutor lives or works here and may confirm this plainly; "
                    "this is ordinary local knowledge, not a secret. A denial would be "
                    "factually wrong.",
                ]
            if service_location is None:
                return [
                    "DIRECT QUESTION GROUNDING",
                    "The player is asking whether a specific local service exists.",
                    "Authorized answer: nenhum serviço confirmado desse tipo existe por perto.",
                    "A plain denial or admission of not knowing is the correct response here.",
                ]

    # Phase 24J.4 — Issue 1, a second live-confirmed source of the SAME
    # relational-geography hallucination: "Onde fica a ferraria?" is a
    # SERVICE-subject, non-existence question with no grounding branch of
    # its own, so app.ai.validation.contract._targeted_relevance_repair
    # (triggered whenever the relevance check rejects a draft for an
    # UNRELATED reason — confirmed live: "no topical acknowledgment") had
    # no authorized fact to give the model and fell to its own generic
    # "answer coherently or admit not knowing" instruction — free rein to
    # invent a wrong direction AND fabricated street names in one pass,
    # entirely unchecked (the repair candidate is only re-validated for
    # hidden names and relevance, never canon/geography). Grounding this
    # up front closes that gap at the source, the same way the two
    # branches above already do for identity/existence.
    if subject == ConversationalSubject.SERVICE and not is_existence_question(player_input):
        service_type = service_type_asked_about(player_input)
        if (
            service_type is not None
            and state.location is not None
            and re.search(r"\bonde\b|\bfica\b|\bdire[çc][ãa]o\b", player_input, re.IGNORECASE)
        ):
            connection_row = (
                db.query(LocationConnection, Location)
                .join(Location, Location.id == LocationConnection.to_location_id)
                .filter(
                    LocationConnection.from_location_id == state.location.id,
                    LocationConnection.active.is_(True),
                    Location.type == service_type,
                )
                .first()
            )
            if connection_row is not None:
                connection, service_location = connection_row
                direction = connection.direction or "direção não registrada"
                route_kind = connection_type_label_pt(connection.connection_type)
                return [
                    "DIRECT QUESTION GROUNDING",
                    "The player is asking WHERE a specific local service is.",
                    f"Authorized answer: fica a {direction}, por uma {route_kind}.",
                    "This is the ONLY authorized direction/route for this destination — never "
                    "state a different direction, invent a street/landmark name, or merge this "
                    "with a different real connection.",
                ]

    # Simplification Pass S1.3 — PRICE. A direct price question ("Quanto
    # custa um quarto?") normally happens standing inside the service
    # itself, talking to the person who runs it — the price is looked up
    # for the CURRENT location first (the common case), falling back to
    # a connected service location of that type only if the player is
    # asking about a DIFFERENT service from elsewhere (mirrors the
    # existence/direction branches above). No fixed price anywhere in
    # the economy model existed for this before this phase (confirmed
    # by a full-codebase search) — grounding an honest "no price
    # established" is just as important here as grounding a real number:
    # either way, the model is never left to invent one.
    if _WAGE_QUESTION_PATTERN.search(_strip_accents_lower(player_input)) and state.location is not None:
        from app.db.models.job import Job

        jobs = (
            db.query(Job)
            .filter(Job.campaign_id == state.character.campaign_id, Job.location_id == state.location.id)
            .order_by(Job.id)
            .all()
        )
        if len(jobs) == 1 and _npc_is_present_at(active_npc, state.location.id):
            job = jobs[0]
            return [
                "DIRECT QUESTION GROUNDING",
                "The player is asking how much a job here PAYS.",
                f"ECONOMIC SUBJECT: wage of {job.title} at {state.location.name}",
                f"CURRENT OFFER: {job.wage_bronze} bronze.",
                "SPEAKER KNOWS PRICE: yes.",
                f"Authorized answer: {job.wage_bronze} bronze por turno de {_shift_length_pt(job.work_minutes)}.",
                "The active interlocutor is the employer; state this pay plainly and promise "
                "nothing else (no meals, lodging, bonuses or other pay).",
            ]
        if not jobs:
            return [
                "DIRECT QUESTION GROUNDING",
                "The player is asking about pay for work here, but no paid job is posted at "
                "this place. Never invent a wage or an opening.",
            ]
        return [
            "DIRECT QUESTION GROUNDING",
            "The player is asking how much work here pays. Only these jobs and wages exist:",
            *(f"- {job.title}: {job.wage_bronze} bronze por turno de {_shift_length_pt(job.work_minutes)}." for job in jobs),
            "Never invent another wage or promise anything else.",
        ]

    if is_price_question(player_input):
        service_type = service_type_asked_about(player_input)
        service_key = economic_service_asked_about(player_input)
        if service_key is None and state.location is not None:
            service_key = {
                "inn": "lodging",
                "blacksmith": "repair",
                "stable": "stabling",
                "healer": "healing",
            }.get(state.location.type)
        if service_key is not None and state.location is not None:
            if service_type is None or state.location.type == service_type:
                priced_location = state.location
            else:
                priced_location = (
                    db.query(Location)
                    .join(LocationConnection, LocationConnection.to_location_id == Location.id)
                    .filter(
                        LocationConnection.from_location_id == state.location.id,
                        LocationConnection.active.is_(True),
                        Location.type == service_type,
                    )
                    .first()
                )
            if priced_location is not None:
                value = get_service_value(db, priced_location.id, service_key)
                price = current_price(db, value) if value is not None else None
                is_local_resident = _npc_is_present_at(active_npc, priced_location.id)
                if price is not None and is_local_resident:
                    return [
                        "DIRECT QUESTION GROUNDING",
                        "The player is asking the PRICE of a specific local service.",
                        f"ECONOMIC SUBJECT: {service_key} at {priced_location.name}",
                        f"BASE: {price.base_price_bronze} bronze.",
                        f"CURRENT OFFER: {price.current_price_bronze} bronze.",
                        "SPEAKER KNOWS PRICE: yes.",
                        f"Authorized answer: {price.current_price_bronze} bronze.",
                        "The active interlocutor runs or works here and knows this price "
                        "plainly; never state a different number, and never invent a price "
                        "for anything not listed here.",
                    ]
                if value is not None and is_local_resident:
                    return [
                        "DIRECT QUESTION GROUNDING",
                        f"ECONOMIC SUBJECT: {service_key} at {priced_location.name}",
                        f"CLASSIFICATION: {value.classification.value}.",
                        "No numeric market price is authorized; answer naturally according to "
                        "that classification and never invent a number.",
                    ]
                if value is None:
                    return [
                        "DIRECT QUESTION GROUNDING",
                        "The player is asking the PRICE of a specific local service.",
                        "No fixed price is established for this. A genuine admission that "
                        "there's no set price (or an offer to negotiate, if that fits the "
                        "interlocutor), is the correct response — never invent a number.",
                    ]

    return []


# "Quanto paga?", "quanto se ganha?", "qual o salário?" — about work, not a
# price; kept apart so the forge's wage is never answered with a repair price.
_WAGE_QUESTION_PATTERN = re.compile(
    r"\bquanto\b.{0,40}\b(?:paga|pagam|pago|ganha|ganho|recebe|recebo)\b|\bsalario\b"
)


def _shift_length_pt(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    hours_text = f"{hours} hora" + ("s" if hours != 1 else "")
    return f"{hours_text} e {rest} minutos" if rest else hours_text


def _strip_accents_lower(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", (text or "").casefold())
        if not unicodedata.combining(char)
    )


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


# Phase 24J.4 — Issue 3 (Dialogue-Revealed Knowledge). The original
# confirmed bug ("Esta é Elhelm..." never registered as a reveal) traced
# to the OLD "cardal_is_village" fact template ("{village.name} é uma
# vila da região {region.name}.") putting the taught entity in the
# sentence-initial position, which _proper_nouns below always excludes.
# TRIED loosening this function's own "skip the first word" rule to a
# curated allowlist of common words — but that broke a DIFFERENT,
# pre-existing consumer of the SAME function: relevance.py's
# _gives_a_concrete_named_answer reuses this on ARBITRARY narrator
# output, not just fact statements. "Nada acontece de imediato." isn't
# in any hand-written common-word allowlist, so "Nada" stopped being
# skipped and got counted as a proper noun — a bare non-answer started
# registering as "gave a concrete named answer" (confirmed regression:
# test_case_e_nothing_happens_fallback_to_available_npc_is_rejected went
# from correctly REJECTED to incorrectly ACCEPTED). REVERTED — this
# function is unchanged from before this phase. The real fix for Issue 3
# lives at the SOURCE instead: world/seed.py's fact templates were
# reworded so the taught entity is never sentence-initial in the first
# place ("Esta vila se chama {village.name}." — "Esta" is the skippable
# first word, {village.name} isn't).
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
    quest_reveal = _quest_existence_is_revealed(fact, narrated_text)
    if quest_reveal is not None:
        return quest_reveal
    if _service_route_is_revealed(fact, narrated_text):
        return True
    names = _proper_nouns(fact.statement)
    if not names:
        return False
    normalized_text = _normalized(narrated_text)
    return all(
        re.search(rf"\b{re.escape(_normalized(name))}\b", normalized_text)
        for name in names
    )


# Quest and transported-guild existence facts carry their public name in
# quotes; naming it is what reveals them.
_QUEST_EXISTENCE_FACT_KEY = re.compile(r"^(?:quest|organization):[^:]+:exists$")
_QUOTED_QUEST_TITLE = re.compile(r'["“](?P<title>.+?)["”]')


def _quest_existence_is_revealed(
    fact: KnownFact,
    narrated_text: str,
) -> bool | None:
    """Match a quest reveal by its title, not by every word in its objectives.

    The fallback before ``:`` keeps facts created by older saves readable;
    new facts use the quoted, description-free statement emitted by
    ``create_quest``.
    """
    if _QUEST_EXISTENCE_FACT_KEY.fullmatch(fact.fact_key) is None:
        return None
    match = _QUOTED_QUEST_TITLE.search(fact.statement)
    title = match.group("title") if match is not None else fact.statement.split(":", 1)[0]
    normalized_title = _normalized(title.strip())
    if not normalized_title:
        return False
    return re.search(
        rf"\b{re.escape(normalized_title)}\b",
        _normalized(narrated_text),
    ) is not None


_SERVICE_ROUTE_STATEMENT = re.compile(r"^Da praça de .+?, (?P<service>.+) fica a (?P<direction>[\wç-]+)\.$")


def _service_route_is_revealed(fact: KnownFact, narrated_text: str) -> bool:
    """A local naturally says "o quadro está a nordeste", never the full
    "Quadro de Avisos de Ravhelm" (confirmed in playtest: the directions were
    given twice and still never learned). The service's kind (its head word)
    and the correct direction within one sentence or the next ("A estalagem?
    Fica a leste.") count; the direction keeps two services of one kind (both
    guilds) apart.
    """
    if not fact.fact_key.startswith("public_service_route:"):
        return False
    match = _SERVICE_ROUTE_STATEMENT.match(fact.statement)
    if match is None:
        return False
    head_word = _normalized(match.group("service").split()[0])
    direction = _normalized(match.group("direction"))
    sentences = re.split(r"(?<=[.!?])\s+|\n+", _normalized(narrated_text))
    return any(
        re.search(rf"\b{re.escape(head_word)}\b", sentences[index])
        and re.search(rf"\b{re.escape(direction)}\b", " ".join(sentences[index:index + 2]))
        for index in range(len(sentences))
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
    # Phase 24N — RAG RESULT != TRUTH (master plan's own principle): the
    # NPC/PLAYER memory sections just above already carry this exact
    # caveat ("Memories describe remembered events or claims; they are
    # not automatic world truth"); this retrieved-knowledge tail pulls
    # from a different source (IndexedKnowledgeDocument, not Memory) and
    # was missing the equivalent warning, even though it's exactly as
    # capable of describing something that predates a later authoritative
    # change (documents_current already excludes anything superseded —
    # Phase 18M — but "current" still means "not superseded," not
    # "guaranteed still narratively relevant this exact turn").
    return (
        format_ranked_documents(budgeted.included)
        + "\nRetrieved knowledge describes past or background material; it never overrides "
        "the current authoritative state shown elsewhere in this context."
    )


def build_narrative_context(
    db: Session,
    state: GameStateSnapshot,
    active_interlocutor: str | None = None,
    player_input: str = "",
    active_simulated_player: str | None = None,
) -> NarrativeContext:
    """Build the structured scene context while separating truth,
    perception and knowledge. Phase 24C — this used to be build_context()
    itself, returning the final joined string directly; build_context()
    below is now a thin wrapper (str = build_narrative_context(...).serialize()),
    kept for every existing caller that only ever wanted the flat text
    Ollama receives. Nothing about what's gathered or how knowledge
    filtering works changed — see NarrativeContext's own docstring."""
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
            *_travel_companion_lines(db, state.character.id),
        ]
    )
    world_section = "\n".join(
        [
            "CURRENT WORLD",
            f"Time: Ano {wt.year}, Mês {wt.month}, Dia {wt.day}, {wt.hour:02d}:{wt.minute:02d} "
            "(only for light and period of day; never state a clock time in the narration)",
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
        # Phase 24J.1 — Name/Region are a private proper noun (the player
        # may not know it yet); Type is what anyone physically present can
        # already tell just by looking around, regardless of whether its
        # NAME is known. Bundling both under one undifferentiated "private"
        # label previously let the model express uncertainty about WHETHER
        # they were even in a village at all, when only the village's NAME
        # should ever be in doubt (a real live-playtest failure — a
        # transported person unsure of the settlement's name also became
        # unsure whether it was a village). The explicit annotations below
        # keep that distinction unmissable at the point of use.
        location_lines.extend(
            [
                f"Name: {state.location.name} (HIDDEN — a private proper noun; do not state it "
                "unless the player already knows it or an authorized interlocutor may reveal it)",
                f"Type: {state.location.type.upper()} (DIRECTLY PERCEPTIBLE — anyone physically "
                "present can tell this much just by looking around, e.g. that they are standing "
                "in a village, independent of whether its NAME is known — never express "
                "uncertainty about this)",
                f"Region: {state.region.name if state.region else 'unknown'} "
                "(HIDDEN — same rule as Name)",
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
                f"({_clip(npc.role, 120)}{_gender_note(npc.name)}; activity={npc.activity}"
                f"{_first_meeting_note(db, state.character, npc)}; "
                f"appearance={npc_appearance_pt(db, state.character.campaign_id, npc)})"
            )
            for npc in state.nearby_npcs[:MAX_VISIBLE_ENTITIES]
        ] or ["- none"]
    )
    visible_lines.append(
        "Describe each person only with their listed appearance (hair, eyes, age) — the "
        "player identifies people by what you describe, so never invent a beard, hair or eye "
        "colour, scar or build that is not listed."
    )
    visible_lines.append(
        "When a person has a gender listed, make every Portuguese word about them agree "
        "with it (ela/ele, a ferreira/o ferreiro, cansada/cansado)."
    )
    visible_lines.append(
        "Only people listed in this section may be singled out in narration. "
        "Before a name is learned, use the registered role as the stable player-facing reference; "
        "never invent a physical description or a distinct local bystander."
    )
    visible_lines.append("VISIBLE TRANSPORTED PEOPLE")
    visible_lines.extend(
        [
            (
                f"- {_transported_label(db, state.character, player)} "
                f"(Level {player.level}{_gender_note(player.name)}; "
                f"appearance={ensure_transported_features(db, player)} Wears the transported outfit.)"
            )
            for player in state.nearby_simulated_players[:MAX_VISIBLE_ENTITIES]
        ]
        or ["- none"]
    )
    if state.nearby_simulated_players:
        # Identical for everyone: stated once, not once per person.
        visible_lines.append(f"The transported outfit: {TRANSPORTED_OUTFIT_APPEARANCE}")
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
                f"Role: {active_npc.role}{_gender_note(active_npc.name)}",
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
                f"Name: {active_transported.name}{_gender_note(active_transported.name)}",
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
                    f"{_clip(transported_appearance(ensure_transported_features(db, active_transported)), 800)}"
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
                _transported_guild_line(db, active_transported.id),
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

    npc_knowledge_section = "\n".join(["NPC KNOWLEDGE", *_grouped_npc_knowledge_lines(npc_facts)])
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
        quest_lines.append(f"- {_clip(quest.name, 160)} [{link.status}]{_quest_schedule_note(db, state.character, quest)}")
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
    shop_lines = [
        *_nearby_shops_context_lines(db, state.character),
        *_settlement_jobs_context_lines(db, state.character),
    ]
    input_canon_lines = [
        "PLAYER INPUT CANON CHECK",
        *_build_input_canon_check(db, state, player_input, npc_facts, player_facts),
        "The player's wording never changes canon by itself.",
    ]
    inventory_context = build_narrator_inventory_context(
        state.inventory,
        player_input,
    )

    ctx = NarrativeContext(
        player=player_section,
        inventory=inventory_context,
        world=world_section,
        location="\n".join(location_lines),
        perception="\n".join(perception_lines),
        known_routes="\n".join(known_route_lines),
        current_location_knowledge="\n".join(current_location_knowledge_lines),
        spatial_knowledge=spatial_knowledge_section,
        visible_npcs="\n".join(visible_lines),
        combat="\n".join(combat_lines) if combat_lines else "",
        active_npc="\n".join(active_lines),
        active_transported="\n".join(active_transported_lines),
        direct_question_grounding="\n".join(
            _direct_question_grounding_lines(
                db, player_input, state, active_npc, location_name_known
            )
        ),
        organizations="\n".join(organization_lines),
        currency="\n".join(currency_lines),
        regional="\n".join(regional_lines) if regional_lines else "",
        local_economy="\n".join(local_economy_lines) if local_economy_lines else "",
        shops="\n".join(shop_lines),
        npc_knowledge=npc_knowledge_section,
        player_knowledge=player_knowledge_section,
        npc_memories=npc_memory_section,
        player_memories=player_memory_section,
        retrieved_long_term=_retrieved_long_term_context(db, state, active_npc, scene_subjects),
        input_canon_check="\n".join(input_canon_lines),
        quests="\n".join(quest_lines),
        techniques="\n".join(technique_lines),
        canon_rule=(
            "CANON RULE\nOnly registered structured data and supplied knowledge are persistent facts. "
            "Missing information is not permission to create geography, buildings, history, "
            "religion, safety claims, important NPCs or other canon."
        ),
    )
    logger.debug("CANONICAL LOCATION CONTEXT\n%s", ctx.location)
    logger.debug("ACTIVE NPC CONTEXT\n%s", ctx.active_npc)
    logger.debug("ACTIVE TRANSPORTED PERSON CONTEXT\n%s", ctx.active_transported)
    logger.debug("NPC KNOWLEDGE\n%s", ctx.npc_knowledge)
    logger.debug("PLAYER KNOWLEDGE\n%s", ctx.player_knowledge)
    budget_result = apply_context_budget(ctx)
    return budget_result.context


def build_context(
    db: Session,
    state: GameStateSnapshot,
    active_interlocutor: str | None = None,
    player_input: str = "",
    active_simulated_player: str | None = None,
) -> str:
    """Thin wrapper over build_narrative_context() for every caller that
    only ever wanted the flat text Ollama receives — the vast majority
    of the codebase, including narrator.narrate()'s own `context: str`
    parameter, unchanged by Phase 24C. Identical to what this function
    itself used to build directly before the structured seam existed,
    except when the combined context exceeds Phase 24M's global budget
    — build_narrative_context() itself applies that trim before
    returning, so this and NarrativeContext.serialize() always agree."""
    final_context = build_narrative_context(
        db, state, active_interlocutor, player_input, active_simulated_player
    ).serialize()
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
    """Phase 24A.1 — deliberately NOT a raw "PLAYER: ...\\nNARRATOR: ..."
    transcript anymore. That literal alternating-label format was a real,
    confirmed root cause (Phase 24A live audit): the model was shown its
    own conversation history in exactly the shape it later reproduced as
    a fabricated multi-turn continuation, because nothing distinguished
    "this is what already happened" from "this is a script to continue."
    The new format wraps every past turn in explicit historical framing
    and an unambiguous instruction not to continue it — same underlying
    information (player speech vs. narrated response, in order), just no
    longer shaped like text a completion model would want to extend.

    Turns are reconstructed from get_recent_story_log's own invariant
    (app.services.story_log._entries_from_events): each STORY_EXCHANGE
    event contributes exactly one adjacent (player, narrator) pair, in
    that order; only WORLD_STARTED ever contributes a lone leading
    narrator-only entry (no player turn preceded it). Pairing walks the
    list respecting that shape rather than assuming a fixed stride, so a
    slice that happens to keep or drop the leading singleton never
    desynchronizes the pairing.
    """
    recent = entries[-max_entries:]
    if not recent:
        return "(nenhuma troca anterior nesta cena)"

    def _clipped(text: str) -> str:
        text = text.strip()
        if len(text) > MAX_HISTORY_ENTRY_CHARS:
            text = f"{text[:MAX_HISTORY_ENTRY_CHARS]}…"
        return text

    def _response_label(entry) -> str:
        # Phase 24D — attribute a past narrated turn to the specific NPC
        # the backend already resolved as active for it, when known
        # (getattr, not direct access: plain HistoryEntry-shaped objects
        # without npc_name — most unit-test doubles — still work
        # unchanged, they just get the generic label).
        npc_name = getattr(entry, "npc_name", None)
        return f"Resposta de {npc_name} anteriormente" if npc_name else "Resposta narrada anteriormente"

    blocks: list[str] = []
    turn_number = 0
    index = 0
    if recent[0].kind != "player":
        blocks.append(
            "Narração inicial da cena (não é uma fala do jogador):\n"
            f'"{_clipped(recent[0].text)}"'
        )
        index = 1

    while index < len(recent):
        entry = recent[index]
        if entry.kind == "player" and index + 1 < len(recent) and recent[index + 1].kind != "player":
            turn_number += 1
            response_entry = recent[index + 1]
            blocks.append(
                f"Turno {turn_number}:\n"
                f'O jogador disse anteriormente: "{_clipped(entry.text)}"\n'
                f'{_response_label(response_entry)}: "{_clipped(response_entry.text)}"'
            )
            index += 2
        else:
            # Defensive fallback for a shape the (player, narrator) pair
            # invariant doesn't cover — never silently drop an entry.
            label = "O jogador disse anteriormente" if entry.kind == "player" else _response_label(entry)
            blocks.append(f'{label}: "{_clipped(entry.text)}"')
            index += 1

    return (
        "HISTÓRICO DE TROCAS RECENTES\n\n"
        "As entradas abaixo descrevem turnos ANTERIORES desta cena. São apenas "
        "contexto histórico, nunca uma transcrição para continuar. Não gere um "
        "novo turno do jogador. Não continue este histórico como se fosse a "
        "próxima fala.\n\n"
        + "\n\n".join(blocks)
        + "\n\nFIM DO HISTÓRICO DE TROCAS RECENTES"
    )
