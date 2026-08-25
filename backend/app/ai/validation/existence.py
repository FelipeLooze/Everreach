"""Phase 24J.4 — Issue 2 (False Factual Denial).

Confirmed live: the player asked "Existe alguma loja geral na vila?" and a
resident NPC answered "Não há nenhuma loja geral propriamente dita aqui" —
a clean, on-topic, RELEVANT denial per app.ai.validation.relevance's own
contract (it addresses the question). But a real "Loja Geral" DOES exist,
one hop from the village, and the very next player action successfully
walked right into it.

The governing spec is explicit that these are three SEPARATE questions
that must stay separate:
    RELEVANCE — did the NPC address the question? (relevance.py's job)
    KNOWLEDGE — what does this NPC know?
    TRUTH     — what is actually true?

This module is the TRUTH layer, and only for the narrow case the spec
names: an EXISTENCE/AVAILABILITY question about a specific settlement
service (inn/blacksmith/shop/...), where the active interlocutor is
established as a LOCAL RESIDENT (the same "ambient local knowledge"
principle already used for the settlement's own name, Phase 24J.1) —
mirroring KNOWLEDGE. No NPC deception/lying system exists anywhere in this
codebase (confirmed by search, not assumed) — per the spec's own explicit
instruction not to invent one, every confident denial of a real, locally-
knowable service is treated as a generation error, not inferred as an
in-character lie. Honest ignorance ("não sei") is a legitimate answer and
is never flagged — this validator only fires on a CONFIDENT denial
pattern, checked as a genuinely separate case from relevance.py's own
_IGNORANCE_MARKERS (reused here rather than re-defined).
"""
import re

from sqlalchemy.orm import Session

from app.ai.conversational_act import (
    ConversationalSubject,
    classify_subject,
    is_existence_question,
    service_type_asked_about,
)
from app.ai.narrator import _normalized
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator
from app.ai.validation.relevance import _IGNORANCE_MARKERS
from app.core.logging import get_logger
from app.db.models.location import Location, LocationConnection
from app.db.models.npc import NPC

logger = get_logger("narration")

_CONFIDENT_DENIAL_PATTERN = re.compile(
    r"\bnao\s+ha\b|\bnao\s+existe\b|\bnao\s+tem(?:os)?\b|\bnao\s+possu[io](?:mos)?\b",
    re.IGNORECASE,
)

_FALSE_DENIAL_MESSAGE = (
    "a resposta nega com confiança a existência de um serviço que existe e é "
    "conhecido localmente; corrija confirmando a existência (o interlocutor é "
    "residente local) ou reescreva como admissão honesta de desconhecimento — "
    "nunca mantenha uma negação confiante de algo que existe"
)


def service_location_near(db: Session, location_id: str, service_type: str) -> Location | None:
    """The REAL, structural ground truth: is a Location of this service
    type connected FROM the given location? Deliberately NOT gated by
    player discovery — a resident NPC's own local knowledge does not
    depend on whether the PLAYER has looked around yet."""
    return (
        db.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(
            LocationConnection.from_location_id == location_id,
            LocationConnection.active.is_(True),
            Location.type == service_type,
        )
        .first()
    )


@register_validator
def validate_service_existence_denial(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    if not proposal.text.strip() or not claims:
        return []
    if classify_subject(proposal.player_input) != ConversationalSubject.SERVICE:
        return []
    if not is_existence_question(proposal.player_input):
        return []
    service_type = service_type_asked_about(proposal.player_input)
    if service_type is None or proposal.location_id is None:
        return []

    service_location = service_location_near(db, proposal.location_id, service_type)
    if service_location is None:
        # Nothing to falsely deny — a denial here may well be true.
        return []

    if proposal.active_npc_id is None:
        return []
    active_npc = db.get(NPC, proposal.active_npc_id)
    # Same ambient-local-knowledge gate 24J.1 established for the
    # settlement's own name: only a resident is treated as authoritatively
    # knowledgeable about the settlement's own services. A non-resident's
    # wrong denial is a more defensible "genuinely doesn't know," not a
    # generation error, and is intentionally left unflagged.
    if active_npc is None or active_npc.location_id != proposal.location_id:
        return []

    normalized_response = _normalized(proposal.text)
    if _IGNORANCE_MARKERS.search(normalized_response):
        return []
    if not _CONFIDENT_DENIAL_PATTERN.search(normalized_response):
        return []

    logger.info(
        "false service-existence denial detected: service_type=%s destination=%s "
        "npc=%s campaign=%s",
        service_type,
        service_location.id,
        active_npc.id,
        campaign_id,
    )

    return [
        Violation(
            claim_index=claim.index,
            category=ClaimCategory.SERVICE_EXISTENCE,
            reason=_FALSE_DENIAL_MESSAGE,
        )
        for claim in claims
    ]
