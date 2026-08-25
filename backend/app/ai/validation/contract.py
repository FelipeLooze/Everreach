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

from app.ai.llm_service import LLMService
from app.ai.narrator import (
    NarrationMode,
    _direct_question_grounding_fact,
    _direct_question_grounding_is_explicit_ignorance,
    _find_hidden_name_violations,
    _normalized,
    _OBSERVATION_TURN_PATTERN,
    _strip_prompt_leak,
    _system_prompt_for,
)
from app.ai.validation.claims import ClaimCategory, NarrativeClaim, extract_claims
from app.ai.validation.fallback import safe_fallback_narration
from app.ai.validation.trace import log_validation_trace

# Phase 19Q — below this length, a repaired narration is treated as
# incoherent fragments rather than a standalone scene beat, and Phase
# 19R's safe fallback is used instead of returning something this thin.
MIN_COHERENT_REPAIR_CHARS = 10


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


def _targeted_relevance_repair(
    llm_service: LLMService, proposal: NarrativeProposal
) -> str | None:
    """Phase 24J.1 Step 6 — Tier 2 repair, but scoped to exactly one
    failure mode: a NOT_ADDRESSED conversational-relevance violation.
    One narrow, question-aware rewrite through the same LLM the narrator
    already uses (explicitly authorized by the spec: "an additional
    local LLM call for targeted repair is authorized if needed"), naming
    the current question, the active speaker, and exactly what they're
    backend-authorized to know — never inventing anything, never
    touching the protagonist's own speech/actions. Bounded to a single
    attempt (no loop); the hidden-name guard and relevance classifier
    are both re-checked on the result so a narrow rewrite like this can
    never smuggle in a name the player doesn't know or silently fail to
    fix the very thing it was asked to fix.
    """
    if not proposal.active_npc_name:
        return None

    fact = _direct_question_grounding_fact(proposal.context)
    if fact:
        known_instruction = f"O que o interlocutor está autorizado a dizer: {fact}"
    elif _direct_question_grounding_is_explicit_ignorance(proposal.context):
        known_instruction = (
            "Não há uma resposta confirmada disponível para o interlocutor. Ele deve "
            "admitir que não sabe, ou recusar responder — nunca inventar uma resposta."
        )
    else:
        known_instruction = (
            "Não há um fato específico pré-aprovado para esta pergunta. Responda de forma "
            "coerente e grounded com o que o interlocutor plausivelmente saberia, ou admita "
            "desconhecimento — nunca invente fatos de mundo (nomes, lugares, história)."
        )

    repair_prompt = (
        f'O jogador perguntou/pediu isto no turno atual: "{proposal.player_input.strip()}"\n\n'
        f"O interlocutor ativo é {proposal.active_npc_name}.\n"
        f"{known_instruction}\n\n"
        "A resposta anterior não reconheceu essa pergunta de forma alguma — mudou de assunto "
        "sem recusar, evadir ou admitir desconhecimento. Reescreva SOMENTE a resposta "
        "narrativa/fala do interlocutor respondendo diretamente a isso, em no máximo dois "
        "parágrafos curtos, em português do Brasil. Não gere fala, pensamentos ou ações "
        f"voluntárias para {proposal.character_name}."
    )

    try:
        raw = llm_service.generate(_system_prompt_for(proposal.mode), repair_prompt)
    except Exception:
        return None

    candidate = _strip_prompt_leak(raw).strip()
    if not candidate:
        return None

    if _find_hidden_name_violations(candidate, proposal.context, proposal.active_npc_name):
        return None

    # Deferred import: app.ai.validation.relevance imports this module at
    # its own module level (it registers a validator here), so importing
    # it back at contract.py's module level would be circular. By call
    # time both modules are already fully loaded.
    from app.ai.validation.relevance import RelevanceOutcome, classify_relevance

    outcome = classify_relevance(
        proposal.player_input, candidate, proposal.active_npc_name, proposal.context
    )
    if outcome == RelevanceOutcome.NOT_ADDRESSED:
        return None
    return candidate


def _targeted_service_existence_repair(
    llm_service: LLMService, proposal: NarrativeProposal
) -> str | None:
    """Phase 24J.4 — mirrors _targeted_relevance_repair's shape exactly
    (same grounding-fact source, same hidden-name/relevance re-check
    safety net), but with a corrected framing: the previous draft DID
    address the question (it's topically relevant) — it just confidently
    denied something that demonstrably exists. Reusing the relevance
    repair's "did not acknowledge this at all" phrasing verbatim would be
    factually wrong about what actually happened.
    """
    if not proposal.active_npc_name:
        return None

    fact = _direct_question_grounding_fact(proposal.context)
    if not fact:
        return None

    repair_prompt = (
        f'O jogador perguntou isto no turno atual: "{proposal.player_input.strip()}"\n\n'
        f"O interlocutor ativo é {proposal.active_npc_name}, residente local.\n"
        f"Fato autorizado: {fact}\n\n"
        "A resposta anterior negou isso com confiança, mas o fato acima é verdadeiro — o "
        "interlocutor conhece bem sua própria vila. Reescreva SOMENTE a resposta narrativa/"
        "fala do interlocutor confirmando esse fato, em no máximo dois parágrafos curtos, em "
        f"português do Brasil. Não gere fala, pensamentos ou ações voluntárias para "
        f"{proposal.character_name}."
    )

    try:
        raw = llm_service.generate(_system_prompt_for(proposal.mode), repair_prompt)
    except Exception:
        return None

    candidate = _strip_prompt_leak(raw).strip()
    if not candidate:
        return None

    if _find_hidden_name_violations(candidate, proposal.context, proposal.active_npc_name):
        return None

    # Deferred import — same circular-import reason as _targeted_relevance_repair.
    from app.ai.narrator import _normalized
    from app.ai.validation.existence import _CONFIDENT_DENIAL_PATTERN

    if _CONFIDENT_DENIAL_PATTERN.search(_normalized(candidate)):
        return None
    return candidate


def _grounded_fallback_narration(proposal: NarrativeProposal) -> str:
    """Phase 24J.1 Steps 7/9 — the generic scripted fallback ("Nada
    acontece de imediato." / "{npc} permanece em silêncio.") must never
    be the FINAL answer to a direct question aimed at an available
    active NPC, even after targeted repair (above) fails or no
    LLMService was supplied. A genuine backend-authorized fact or a
    plain admission of not knowing is always preferable to silence for
    someone who is right there and was directly asked. Falls back to
    the original scripted line only when there's no active interlocutor,
    or the grounding context has nothing to offer either.
    """
    if not proposal.active_npc_name:
        return safe_fallback_narration(proposal.mode, proposal.active_npc_name)

    fact = _direct_question_grounding_fact(proposal.context)
    if fact:
        return f"— {fact} — responde {proposal.active_npc_name}."
    if _direct_question_grounding_is_explicit_ignorance(proposal.context):
        return f"— Não sei dizer ao certo — responde {proposal.active_npc_name}."
    return safe_fallback_narration(proposal.mode, proposal.active_npc_name)


def _repair(
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
    violations: list[Violation],
    llm_service: LLMService | None = None,
) -> str:
    """Phase 19Q — Narrative Repair, tier 1 of the spec's own REPAIR
    PRIORITY ("remove invalid clause if prose remains coherent"): drop
    every claim a violation referenced, keep the rest, rejoin. Falls
    through to Phase 19R's safe fallback when what survives is empty or
    too fragmentary to stand alone as a scene beat (MIN_COHERENT_
    REPAIR_CHARS) — never returns a bare empty string to the player.

    Tier 2 (24J.1): scoped specifically to a conversational-relevance
    NOT_ADDRESSED violation — see _targeted_relevance_repair. Every
    other violation category still falls straight to the scripted
    fallback (Tier 3 rewrite-using-validated-facts stays out of scope,
    as before) — this is a single bounded pass, never a loop.
    """
    invalid_indices = {violation.claim_index for violation in violations}
    kept = [claim.text for claim in claims if claim.index not in invalid_indices]
    repaired = " ".join(kept).strip()
    if len(repaired) >= MIN_COHERENT_REPAIR_CHARS:
        return repaired

    is_relevance_failure = any(
        violation.category == ClaimCategory.CONVERSATIONAL_RELEVANCE for violation in violations
    )
    # Phase 24J.4 — a false service-existence denial gets the SAME
    # question-aware repair treatment as a NOT_ADDRESSED relevance
    # failure: silence is never better than a real, backend-supplied
    # fact for a direct question aimed at an available, knowledgeable
    # active NPC.
    is_service_existence_failure = any(
        violation.category == ClaimCategory.SERVICE_EXISTENCE for violation in violations
    )
    if not is_relevance_failure and not is_service_existence_failure:
        return safe_fallback_narration(proposal.mode, proposal.active_npc_name)

    if llm_service is not None:
        targeted = (
            _targeted_service_existence_repair(llm_service, proposal)
            if is_service_existence_failure
            else _targeted_relevance_repair(llm_service, proposal)
        )
        if targeted is not None:
            return targeted
    return _grounded_fallback_narration(proposal)


def validate_narrative_proposal(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    llm_service: LLMService | None = None,
) -> NarrativeValidationResult:
    """Runs every registered validator (empty until 19D) against the
    proposal's extracted claims and repairs (drops) whatever any of them
    reject. Accepts the proposal unchanged when there are no violations
    — including, still today, whenever no validator is registered."""
    known_names = (proposal.active_npc_name,) if proposal.active_npc_name else ()
    # Phase 24J.5 — mirrors narrator.narrate()'s own is_observation_turn
    # computation exactly (same pattern, same field) so this independent
    # second pass over the already-accepted text cannot disagree with it
    # about whether THIS turn's backend-resolved mechanical fact was an
    # observation action.
    is_observation_turn = bool(_OBSERVATION_TURN_PATTERN.search(_normalized(proposal.mechanical_summary)))
    claims = extract_claims(
        proposal.text,
        character_name=proposal.character_name,
        known_names=known_names,
        is_observation_turn=is_observation_turn,
    )

    violations: list[Violation] = []
    for validator in _VALIDATORS:
        violations.extend(validator(db, campaign_id, proposal, claims))

    log_validation_trace(proposal, claims, violations)

    if not violations:
        return NarrativeValidationResult(valid=True, final_text=proposal.text, violations=[])

    return NarrativeValidationResult(
        valid=False,
        final_text=_repair(proposal, claims, violations, llm_service),
        violations=[violation.reason for violation in violations],
    )
