"""Phase 19K — NPC State Validator.

Genuinely new (narrator.py has no database access). Reuses Phase 19H's
same conservative "name opens the sentence" subject detection — an NPC
recorded as dead (NPC.alive is False) narrated performing any action is
rejected; the spec's own clean example ("Osgar is dead... 'Osgar enters
the room.' Reject.").

Deliberately scoped to alive/dead only for this subphase — consciousness
(NPC.incapacitated), imprisonment, and travel status would each need
their own curated "which verbs require consciousness/freedom of
movement" vocabulary to check safely without over-rejecting (Phase
19G's lesson); documented as deferred, not silently ignored.
"""
import re

from sqlalchemy.orm import Session

from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator
from app.ai.validation.spatial import _opens_with_name
from app.db.models.npc import NPC

_ACTION_VERBS = re.compile(
    r"\b(entra\w*|chega\w*|caminha\w*|fala\w*|diz\w*|sorri\w*|acena\w*|"
    r"levanta\w*|anda\w*|corre\w*|ataca\w*|olha\w*|observa\w*|aproxima\w*|"
    r"responde\w*|pergunta\w*|acena\w*|segura\w*|pega\w*)\b",
    re.IGNORECASE,
)


@register_validator
def validate_npc_state(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    dead_npcs = (
        db.query(NPC)
        .filter(NPC.campaign_id == campaign_id, NPC.alive.is_(False))
        .all()
    )
    if not dead_npcs:
        return []

    violations = []
    for claim in claims:
        if not _ACTION_VERBS.search(claim.text):
            continue
        for npc in dead_npcs:
            if _opens_with_name(claim.text, npc.name):
                violations.append(
                    Violation(
                        claim_index=claim.index,
                        category=ClaimCategory.AUTHORITATIVE,
                        reason=(
                            f"'{npc.name}' é narrado(a) agindo, mas está registrado(a) como "
                            f"morto(a)."
                        ),
                    )
                )
    return violations
