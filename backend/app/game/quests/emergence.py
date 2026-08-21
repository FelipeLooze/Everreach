"""Phase 12H — Emergent World Quests.

WORLD FIRST, QUEST SECOND: a Quest here is never spontaneously invented —
it only ever comes from a WorldEvent that already, authoritatively,
happened (NPC_DIED is the first wired case; see _QUEST_WORTHY_EVENT_TYPES).
This module does not generate problems itself — no bridge collapses, no
monster migrations — that would be a world-simulation feature, and none
exists yet to produce such events. Not every problem becomes a quest
(the spec's own critical rule): only the small allow-listed event types
below are treated as quest-worthy at all, and each WorldEvent produces at
most one Quest (source_event_id is the idempotency key).

The LLM only ever phrases a name/description; it never decides that a
Quest should exist (the WorldEvent already decided that by happening),
what happened, or any objective fact. See propose_emergent_quest — a
2-attempt proposal + validation loop mirroring Phase 11J's
propose_and_recognize_technique, but unlike that flow this always
produces a Quest: the underlying event already justifies one existing
either way, so repeated validation failure falls back to a plain,
backend-authored name/description instead of giving up.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.llm_service import LLMService, LLMServiceError
from app.core.enums import EventType, QuestSource
from app.core.logging import get_logger
from app.db.models.event import WorldEvent
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.quest import Quest
from app.db.models.region import Region
from app.game.quests.service import create_quest

logger = get_logger("game")

_PROMPT_PATH = Path(__file__).parents[2] / "ai" / "prompts" / "emergent_quest_naming_system.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_MAX_ATTEMPTS = 2

_QUEST_WORTHY_EVENT_TYPES = {EventType.NPC_DIED}

_NUMERIC_CLAIM_PATTERN = re.compile(
    r"\b\d+([.,]\d+)?\s*"
    r"(de\s+)?"
    r"(moedas?|ouro|prata|dano|%|por\s*cento|dias?|horas?|semanas?|metros?)\b",
    re.IGNORECASE,
)


class EmergentQuestError(Exception):
    pass


@dataclass(frozen=True)
class QuestIdentityProposal:
    name: str
    description: str


def _capitalized_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[A-ZÀ-Ý][\wÀ-ÿ'-]*", text) if len(word) >= 3}


def _proper_nouns(text: str) -> set[str]:
    """Capitalized words in freeform prose, skipping each sentence's own
    first word (capitalized purely by sentence position, not because it's
    a name) — a small multi-sentence extension of the heuristic
    app.ai.context_builder uses for the canon-check, duplicated locally
    since game/ code does not import from ai/ (the dependency runs the
    other way in this codebase). Only for natural-language text (an LLM
    proposal's name/description) — a bare name like "Osgar Vell" is not a
    sentence and must not have its first word skipped; see
    _capitalized_words for that case."""
    words: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        tokens = list(re.finditer(r"\S+", sentence))
        scan_from = tokens[1].start() if len(tokens) > 1 else len(sentence)
        words |= {
            word
            for word in re.findall(r"[A-ZÀ-Ý][\wÀ-ÿ'-]*", sentence[scan_from:])
            if len(word) >= 3
        }
    return words


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _known_names_for_npc_death(db: Session, npc: NPC) -> set[str]:
    known = _capitalized_words(npc.name)
    location = db.get(Location, npc.location_id) if npc.location_id else None
    if location is not None:
        known |= _capitalized_words(location.name)
    region = db.get(Region, npc.region_id) if npc.region_id else None
    if region is not None:
        known |= _capitalized_words(region.name)
    return known


def _fallback_identity(npc: NPC, cause: str) -> QuestIdentityProposal:
    return QuestIdentityProposal(
        name=f"A morte de {npc.name}",
        description=f"{npc.name} morreu ({cause}). Alguém pode querer entender o que houve.",
    )


def _npc_death_summary_text(npc: NPC, cause: str, location: Location | None) -> str:
    lines = [
        "Tipo de evento: morte de NPC",
        f"Nome: {npc.name}",
        f"Causa: {cause or 'desconhecida'}",
    ]
    if location is not None:
        lines.append(f"Local: {location.name}")
    return "\n".join(lines)


def _request_identity_proposal(
    llm_service: LLMService,
    summary_text: str,
    *,
    previous_violations: list[str] | None = None,
) -> QuestIdentityProposal | None:
    prompt = f"Resumo autoritativo do evento:\n{summary_text}"
    if previous_violations:
        prompt += (
            "\n\nSua proposta anterior violou estas regras — proponha de novo, "
            "corrigindo apenas isso:\n- " + "\n- ".join(previous_violations)
        )
    try:
        raw = llm_service.generate(_SYSTEM_PROMPT, prompt)
    except LLMServiceError:
        logger.info("emergent quest naming: LLM unavailable")
        return None
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning("emergent quest naming: could not parse LLM response: %r", raw)
        return None
    name = data.get("name")
    description = data.get("description")
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(description, str) or not description.strip():
        return None
    return QuestIdentityProposal(name=name.strip(), description=description.strip())


def _validate_identity_proposal(
    proposal: QuestIdentityProposal, known_names: set[str]
) -> list[str]:
    """Conservative rejection: anything not grounded in the event's own
    known names, or any invented numeric promise, is rejected. False
    positives just cost a retry (and ultimately the safe backend
    fallback); false negatives would let the LLM invent world facts."""
    text = f"{proposal.name} {proposal.description}"
    violations: list[str] = []

    if _NUMERIC_CLAIM_PATTERN.search(text):
        violations.append(
            "a proposta inclui um valor numérico (moeda, prazo, distância); "
            "isso não foi estabelecido pelo evento de origem"
        )

    mentioned = _proper_nouns(proposal.name) | _proper_nouns(proposal.description)
    unknown = {name for name in mentioned if not any(name in known or known in name for known in known_names)}
    if unknown:
        violations.append(
            "a proposta menciona nome(s) que não constam no evento de origem: "
            + ", ".join(sorted(unknown))
        )

    return violations


def propose_emergent_quest_from_npc_death(
    db: Session,
    campaign_id: str,
    llm_service: LLMService,
    *,
    world_event_id: str,
) -> Quest:
    """The only wired emergent-quest trigger today: an NPC actually died
    (a real, already-logged WorldEvent). Idempotent per world_event_id —
    calling this again for the same event returns the same Quest rather
    than creating a second one."""
    event = db.get(WorldEvent, world_event_id)
    if event is None or event.campaign_id != campaign_id:
        raise EmergentQuestError(f"Evento de mundo desconhecido: {world_event_id}")
    if event.event_type != EventType.NPC_DIED:
        raise EmergentQuestError(
            f"Evento {event.event_type} não é um dos tipos dignos de missão emergente."
        )

    existing = db.query(Quest).filter(Quest.source_event_id == world_event_id).first()
    if existing is not None:
        return existing

    payload = json.loads(event.payload_json)
    npc = db.get(NPC, payload.get("npc_id"))
    if npc is None:
        raise EmergentQuestError(f"NPC do evento {world_event_id} não existe mais.")
    cause = payload.get("cause", "")
    location = db.get(Location, npc.location_id) if npc.location_id else None

    known_names = _known_names_for_npc_death(db, npc)
    summary_text = _npc_death_summary_text(npc, cause, location)
    fallback = _fallback_identity(npc, cause)

    identity = fallback
    violations: list[str] | None = None
    for _attempt in range(_MAX_ATTEMPTS):
        proposal = _request_identity_proposal(
            llm_service, summary_text, previous_violations=violations
        )
        if proposal is None:
            break
        violations = _validate_identity_proposal(proposal, known_names)
        if not violations:
            identity = proposal
            break
        logger.warning(
            "emergent quest naming: proposal for event %s rejected: %s",
            world_event_id,
            violations,
        )

    quest = create_quest(
        db,
        npc.region_id,
        identity.name,
        identity.description,
        source=QuestSource.WORLD_EVENT,
    )
    quest.source_event_id = world_event_id
    db.flush()
    return quest
