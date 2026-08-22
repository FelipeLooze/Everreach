"""Phase 19A — Narrative Validation Contract.

Audit summary (no behavior changed by this module):

- The Narrator (app.ai.narrator.narrate) is called from exactly one
  place today, app.game.engine's action-resolution flow, right after
  context_builder.build_context() produces the scene context and the
  Game Engine has already resolved every mechanical outcome into
  mechanical_summary (a plain string, not a structured object).
- narrator.narrate() already returns raw text (no structured claims)
  and already runs its OWN internal validation before returning: a
  regex/keyword-based hard-violation pass (canon claims, NPC meta-
  awareness, protagonist agency, fabricated player turns, unauthorized
  combatants/speakers, hidden names, unsolicited opening interactions),
  a bounded 2-attempt LLM revision loop, and granular paragraph/
  sentence-level dropping as a last-resort repair before a deterministic
  safe fallback ("Nada acontece de imediato." / "{npc} permanece em
  silêncio."). All of that already exists and stays untouched — it is
  real, working defense against most of what Phase 19 asks for, just
  validated only against the context STRING (no direct database
  access; narrator.py is architecturally forbidden from importing
  sqlalchemy/app.db — see test_only_llm_service_contains_ollama_
  transport_code and test_narrator_only_delegates_text_generation_to_
  llm_service).
- A second, separate, much lighter seam already exists one level up:
  app.ai.narrative_validator.validate(text, canonical_facts) is called
  in engine.py right after narrator.narrate() returns, given a tiny
  canonical_facts dict (app.game.engine.mechanical_summary is not part
  of it; context_builder.build_canonical_facts only currently tracks
  character_alive and dead_npc_names). It is intentionally minimal
  ("full narrative validation is future work") and never repairs
  anything — ValidationResult.text is always exactly the input text
  unchanged; only its `warnings` are ever consulted downstream, and
  only to be logged/surfaced, never to block or rewrite output. THIS
  is where final narration currently bypasses any real validation: a
  hard-violation-free but still factually-wrong narration (e.g. an
  NPC's current location claimed incorrectly, an item invented) sails
  through unmodified today.
- Player input (`text`) and the resolved intent (`intent`, an
  ActionIntentType) are both already in scope in engine.py at the
  narrate() call site — trivially available to a Player Agency
  validator without new plumbing.
- mechanical_summary (already resolved, already in scope) is the
  "resolved mechanical outcome" a Mechanical Outcome Validator (19N)
  will eventually check narration against — currently free text, not
  a structured per-intent result; formalizing that is explicitly out
  of scope for 19A per the FIRST TASK's own instructions.

This module introduces ONLY the shared contract: NarrativeProposal
(everything a future validator needs, gathered once) and
NarrativeValidationResult (what a validator run produces), plus a
pass-through pipeline entry point. No validators run yet — every real
check (19D player agency, 19F canon, 19G knowledge, ... 19P
contradiction) is deliberately deferred. validate_narrative_proposal
always accepts the proposal unchanged; wiring it into engine.py now
(alongside — not replacing — the existing narrative_validator.validate
call) means later subphases attach real behavior here without another
engine.py integration.
"""
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.orm import Session

from app.ai.narrator import NarrationMode
from app.ai.validation.claims import ClaimCategory, NarrativeClaim, extract_claims


@dataclass(frozen=True)
class NarrativeProposal:
    """The Narrator's raw output plus everything a future validator will
    need to judge it. Every field is a copy of something already
    authoritative elsewhere (game_state, context_builder, engine) — this
    object is never itself a source of world state, only a bundle of
    references to it for this one validation pass."""

    text: str
    mode: NarrationMode
    context: str
    mechanical_summary: str
    player_input: str
    recent_history: str
    character_name: str
    character_id: str = ""
    location_id: str | None = None
    active_npc_id: str | None = None
    active_npc_name: str | None = None


@dataclass(frozen=True)
class Violation:
    """One claim (Phase 19B/19C, sentence-granularity) a validator
    rejected, and why. claim_index refers to the claim list
    validate_narrative_proposal extracts from proposal.text — the same
    list every registered validator receives, so repair (Phase 19Q) can
    map every violation straight back to the exact sentence to drop."""

    claim_index: int
    category: ClaimCategory
    reason: str


@dataclass(frozen=True)
class NarrativeValidationResult:
    valid: bool
    final_text: str
    violations: list[str] = field(default_factory=list)


NarrativeValidator = Callable[
    [Session, str, NarrativeProposal, list[NarrativeClaim]], list[Violation]
]

_VALIDATORS: list[NarrativeValidator] = []


def register_validator(fn: NarrativeValidator) -> NarrativeValidator:
    """Phase 19D+ — each validator module (agency, canon, knowledge,
    spatial, ...) registers itself here via this decorator when
    imported. app.ai.validation's package __init__ imports every
    validator module for its registration side effect, so callers only
    ever need `from app.ai.validation import validate_narrative_proposal`
    — never a hand-maintained list of validators to keep in sync."""
    _VALIDATORS.append(fn)
    return fn


def _repair(
    proposal: NarrativeProposal, claims: list[NarrativeClaim], violations: list[Violation]
) -> str:
    """Phase 19D's minimal repair primitive: drop every claim a
    violation referenced, keep the rest, rejoin. This is intentionally
    the simplest tier of the spec's own REPAIR PRIORITY ("1. Remove
    invalid clause if prose remains coherent") — Phase 19Q adds the
    richer tiers (rewrite using validated facts, bounded regeneration)
    on top of this same violations list; Phase 19R adds a true
    scene-grounded fallback for when nothing survives removal."""
    invalid_indices = {violation.claim_index for violation in violations}
    kept = [claim.text for claim in claims if claim.index not in invalid_indices]
    return " ".join(kept).strip()


def validate_narrative_proposal(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
) -> NarrativeValidationResult:
    """Runs every registered validator (empty until 19D) against the
    proposal's extracted claims and repairs (drops) whatever any of them
    reject. Accepts the proposal unchanged when there are no violations
    — including, still today, whenever no validator is registered."""
    known_names = (proposal.active_npc_name,) if proposal.active_npc_name else ()
    claims = extract_claims(
        proposal.text, character_name=proposal.character_name, known_names=known_names
    )

    violations: list[Violation] = []
    for validator in _VALIDATORS:
        violations.extend(validator(db, campaign_id, proposal, claims))

    if not violations:
        return NarrativeValidationResult(valid=True, final_text=proposal.text, violations=[])

    return NarrativeValidationResult(
        valid=False,
        final_text=_repair(proposal, claims, violations),
        violations=[violation.reason for violation in violations],
    )
