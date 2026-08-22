"""Phase 19P — Contradiction Detection.

Uses AUTHORITATIVE STATE (the active NPC's own backstory/personality
text — a real database column), not only textual RAG comparison, per
the spec's explicit instruction. A full general-purpose contradiction
detector (arbitrary attribute vs. arbitrary attribute) needs real NLP
this codebase doesn't have; this subphase instead implements ONE
concrete, narrow, reliable instance of the spec's own worked example —
hair color — as a proof of the mechanism, scoped tightly enough to
avoid false positives (Phase 19G's lesson): it only fires when BOTH the
claim and the NPC's own backstory/personality mention "cabelo" (hair)
together with a color word, and those color words are mutually
exclusive.

Settlement wall-status contradiction (the spec's other worked example)
is not implemented: Location has no structured "walled" field, and
inferring it reliably from free-text description would risk exactly
the false-positive pattern Phase 19G already demonstrated — deferred,
documented, not silently skipped.
"""
import re

from sqlalchemy.orm import Session

from app.ai.narrator import _normalized
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator
from app.db.models.npc import NPC

_HAIR_COLOR_GROUPS: list[set[str]] = [
    {"preto", "preta", "pretos", "pretas", "negro", "negra"},
    {"loiro", "loira", "loiros", "loiras"},
    {"ruivo", "ruiva", "ruivos", "ruivas"},
    {"castanho", "castanha", "castanhos", "castanhas"},
    {"grisalho", "grisalha", "grisalhos", "grisalhas", "branco", "branca"},
]


def _hair_color(text: str) -> str | None:
    normalized = _normalized(text)
    if not re.search(r"\bcabelo\w*\b", normalized):
        return None
    for group in _HAIR_COLOR_GROUPS:
        for word in group:
            if re.search(rf"\b{word}\b", normalized):
                return word
    return None


def _same_group(word_a: str, word_b: str) -> bool:
    return any(word_a in group and word_b in group for group in _HAIR_COLOR_GROUPS)


@register_validator
def validate_contradiction(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    if proposal.active_npc_id is None:
        return []

    npc = db.get(NPC, proposal.active_npc_id)
    if npc is None:
        return []

    established_color = _hair_color(npc.backstory or "") or _hair_color(npc.personality or "")
    if established_color is None:
        return []

    violations = []
    for claim in claims:
        claimed_color = _hair_color(claim.text)
        if claimed_color is None or claimed_color == established_color:
            continue
        if _same_group(claimed_color, established_color):
            continue
        violations.append(
            Violation(
                claim_index=claim.index,
                category=ClaimCategory.AUTHORITATIVE,
                reason=(
                    f"'{claim.text}' contradiz a aparência já estabelecida de "
                    f"{npc.name} (cabelo {established_color})."
                ),
            )
        )
    return violations
