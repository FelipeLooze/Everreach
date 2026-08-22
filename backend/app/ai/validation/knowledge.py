"""Phase 19G — Knowledge & Information Validator.

Two checks, one reused (defense in depth) and one genuinely new:

1. Player-facing hidden information: reuses app.ai.narrator.
   _find_hidden_name_violations — the same check narrator.narrate()
   already runs before returning (a private canonical location/region
   name the player doesn't know must not leak into player-facing
   prose). Phase 18 already filters what reaches the context in the
   first place; this is the defense-in-depth second layer the spec
   explicitly asks for ("Phase 18 should already filter context. Phase
   19 provides defense in depth").

2. NPC speech must respect NPC Knowledge (genuinely new — narrator.py
   has no database access to check this itself): a claim shaped like
   the active NPC's own dialogue (starts with an em dash, matching
   narrator.py's own _is_dialogue_paragraph convention) that names a
   proper noun the NPC has no KnowledgeFact for is rejected — an NPC
   stating "the king died yesterday" when nothing ever taught them that
   fact is exactly the spec's own worked example.
"""
import re

from sqlalchemy.orm import Session

from app.ai.context_builder import _proper_nouns
from app.ai.narrator import _find_hidden_name_violations
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator
from app.core.enums import KnowerType
from app.game.npcs.service import known_facts


_DIALOGUE_PREFIX = re.compile(r"^[—-]\s*")


def _is_npc_dialogue_claim(text: str) -> bool:
    return text.strip().startswith(("—", "-"))


def _dialogue_proper_nouns(text: str) -> set[str]:
    """Strips the leading em-dash before reusing context_builder.
    _proper_nouns, so ITS OWN "skip the sentence's first word" rule
    lands on the dialogue's actual first word — not the dash — as
    intended. Skipping this strip previously turned an ordinary
    sentence-initial capitalized word ("— Bom dia." -> "Bom") into a
    false-positive "unknown name"."""
    return _proper_nouns(_DIALOGUE_PREFIX.sub("", text))


def _fact_subject_names(statement: str) -> set[str]:
    """Every capitalized word in a fact's own statement — unlike
    context_builder._proper_nouns (reused below for claim text), this
    does NOT skip the first word: a Knowledge fact's subject is very
    often stated first ("Osgar nasceu em Cardal."), and skipping it
    would make the NPC appear not to know its own name."""
    return {word for word in re.findall(r"[A-ZÀ-Ý][\wÀ-ÿ'-]*", statement) if len(word) >= 3}


@register_validator
def validate_knowledge(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    violations: list[Violation] = []

    for claim in claims:
        for reason in _find_hidden_name_violations(
            claim.text, proposal.context, proposal.active_npc_name or ""
        ):
            violations.append(
                Violation(claim_index=claim.index, category=ClaimCategory.AUTHORITATIVE, reason=reason)
            )

    if proposal.active_npc_id is not None:
        facts = known_facts(db, campaign_id, KnowerType.NPC, proposal.active_npc_id)
        known_names: set[str] = set()
        for fact in facts:
            known_names |= _fact_subject_names(fact.statement)
        safe_names = known_names | {proposal.active_npc_name or "", proposal.character_name}

        for claim in claims:
            if not _is_npc_dialogue_claim(claim.text):
                continue
            mentioned = _dialogue_proper_nouns(claim.text)
            if not mentioned:
                continue
            # Conservative on purpose: only reject when NONE of the
            # named entities are backed by anything the NPC knows — an
            # NPC mentioning one grounded name alongside one un-granted
            # but plausibly-adjacent one (e.g. their own settlement's
            # region) is a real, already-working reveal mechanic
            # (app.game.engine._teach_facts_revealed_in_narration), not
            # the spec's "invented a fact from nothing" case. Rejecting
            # on ANY partial mismatch previously broke that mechanic.
            if mentioned.isdisjoint(safe_names):
                violations.append(
                    Violation(
                        claim_index=claim.index,
                        category=ClaimCategory.AUTHORITATIVE,
                        reason=(
                            f"{proposal.active_npc_name or 'O NPC'} menciona "
                            f"{', '.join(sorted(mentioned))}, que não consta em seu "
                            f"conhecimento registrado."
                        ),
                    )
                )

    return violations
