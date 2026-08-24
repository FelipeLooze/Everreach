"""Phase 24J / 24J.1 — Conversational Relevance Validation.

The master plan's own words: "This is currently one of the highest-
priority missing guarantees." Detects when the Narrator's response
doesn't meaningfully address the CURRENT player conversational act
(Phase 24E) — the spec's own worked example: "Qual o seu nome?"
answered with "Temos uma ótima estalagem na praça." is invalid random
topic drift, never a legitimate NPC choice.

NPCs ARE allowed to lie, refuse, evade, or plead ignorance — those are
all intentional, grounded responses and must NOT be rejected here.
Only genuine non-acknowledgment (no refusal marker, no ignorance
marker, no evasion marker, no clarification request, and no topical
connection to what was asked at all) is a violation.

Deterministic only, per the plan's explicit "avoid adding another full
LLM generation call to every normal turn merely to judge relevance" —
curated marker phrases plus keyword/proper-noun checks, the same style
already established throughout this codebase (_PERSISTENT_CONCEPTS,
_SPEECH_VERBS, narrator.py's own canon denial_pattern), not a semantic
parse or a second LLM call.

HISTORY — Phase 24J (original): a first attempt enforced NOT_ADDRESSED
for every "must-address" act using generic keyword overlap, and it
broke a real, passing scenario — "como se chama este lugar?" answered
"Isto aqui é Cardal..." shares no literal words with the question at
all (real dialogue paraphrases, it doesn't echo the player's wording
back). The fix at the time was to narrow enforcement to ONLY a
self-identity question ("qual o SEU nome"), using the NPC's own
registered name as the acceptance signal — data-driven and immune to
paraphrase risk, but leaving every other must-address act (including
location/settlement questions) completely unenforced.

HISTORY — Phase 24J.1 (real live playtest failure, this subphase):
that gap was hit for real. A player asked a local innkeeper "Saberia
me informar que vila é essa?" and, on a literal repeat of the question
one turn later, got a bare, near-verbatim generic greeting closer
("Como posso ajudar você hoje?") acknowledging nothing — and it sailed
through validation with zero violations, because QUESTION_LOCATION/
QUESTION_NAME-about-a-settlement was never in the enforced set at all.

THE FIX (24J.1): broaden enforcement to every `_MUST_ADDRESS_ACTS` act,
but do it the same safe way the original identity-only fix did, not by
reverting to naive keyword overlap. `app.ai.conversational_act`'s new
`classify_subject()` (additive, not a replacement of the 9-label act)
gives a small structured "what is this actually about" dimension.
Where a subject has a strong, data-driven acceptance signal available
(SELF_NAME -> the active NPC's own registered name; CURRENT_SETTLEMENT/
CURRENT_LOCATION -> the location's canonical Name field, already parsed
by `narrator._private_location_fields`, the same parser the hidden-name
guard uses), that signal decides ANSWERED outright. Where no such
signal is available for this subject or this context (e.g. no location
Name registered at all, as in the original Cardal scenario), the same
paraphrase-tolerant fallback used since Phase 24J — term overlap OR any
concrete named answer (`_gives_a_concrete_named_answer`) — is what
`classify_relevance` already used to accept "Isto aqui é Cardal...",
and stays the fallback here too. That's what keeps this broadening
from repeating the original regression: the fallback isn't new, it's
already proven safe, it's just no longer gated off from every act
except self-identity.

The outcome taxonomy also expands (24J.1) to the spec's own vocabulary:
ANSWERED, REFUSED, EVADED, ADMITTED_IGNORANCE, REQUESTED_CLARIFICATION,
PLAUSIBLY_MISUNDERSTOOD, NOT_ADDRESSED. A LIED_OR_CONTESTED case is
deliberately NOT a separate detection branch: relevance is about
whether the NPC engaged with the question, not whether what they said
is true — a confident lie looks, to this validator, exactly like a
confident answer (ANSWERED); Canon/knowledge validators are the layer
that would ever dispute the content, not this one. Only NOT_ADDRESSED
is ever turned into a Violation.
"""
import re
from enum import StrEnum

from sqlalchemy.orm import Session

from app.ai.context_builder import _proper_nouns
from app.ai.conversational_act import ConversationalAct
from app.ai.conversational_act import ConversationalSubject
from app.ai.conversational_act import _SERVICE_WORDS
from app.ai.conversational_act import classify as classify_conversational_act
from app.ai.conversational_act import classify_subject
from app.ai.narrator import _mentions, _mentions_canonical_name, _normalized, _private_location_fields
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator
from app.game.npcs.service import _SEARCH_STOP_WORDS

# Acts with nothing mandatory to address (GREETING, STATEMENT) or their
# own dedicated grounding already (FAREWELL, Phase 24E) are out of scope.
_MUST_ADDRESS_ACTS = frozenset(
    {
        ConversationalAct.QUESTION_NAME,
        ConversationalAct.QUESTION_LOCATION,
        ConversationalAct.QUESTION_PERSON,
        ConversationalAct.QUESTION_OBJECT,
        ConversationalAct.REQUEST_INFORMATION,
        ConversationalAct.REQUEST_HELP,
    }
)

_LOCATION_SUBJECTS = frozenset(
    {ConversationalSubject.CURRENT_SETTLEMENT, ConversationalSubject.CURRENT_LOCATION}
)


class RelevanceOutcome(StrEnum):
    ANSWERED = "ANSWERED"
    REFUSED = "REFUSED"
    EVADED = "EVADED"
    ADMITTED_IGNORANCE = "ADMITTED_IGNORANCE"
    REQUESTED_CLARIFICATION = "REQUESTED_CLARIFICATION"
    PLAUSIBLY_MISUNDERSTOOD = "PLAUSIBLY_MISUNDERSTOOD"
    NOT_ADDRESSED = "NOT_ADDRESSED"


_REFUSAL_MARKERS = re.compile(
    r"\b(prefiro\s+nao\s+dizer|nao\s+vou\s+dizer|nao\s+posso\s+dizer|"
    r"nao\s+e\s+da\s+sua\s+conta|isso\s+nao\s+(?:te|lhe)\s+interessa|"
    r"voce\s+nao\s+precisa\s+saber|nao\s+lhe\s+diz\s+respeito)\b",
    re.IGNORECASE,
)
_IGNORANCE_MARKERS = re.compile(
    r"\b(nao\s+sei|nao\s+fac?o\s+ideia|desconhec[oe]|nao\s+tenho\s+certeza|"
    r"nao\s+saberia\s+dizer)\b",
    re.IGNORECASE,
)
_EVASION_MARKERS = re.compile(
    r"\b(prefiro\s+falar\s+sobre|isso\s+agora\s+nao\s+importa|vamos\s+deixar\s+isso|"
    r"mudemos\s+de\s+assunto|melhor\s+falarmos\s+de\s+outra\s+coisa)\b",
    re.IGNORECASE,
)
_CLARIFICATION_MARKERS = re.compile(
    r"\b(como\s+assim|pode\s+repetir|poderia\s+repetir|nao\s+entendi|"
    r"o\s+que\s+voce\s+quer\s+dizer|poderia\s+explicar\s+melhor|"
    r"pode\s+ser\s+mais\s+especifico|quem\s+voce\s+quer\s+dizer)\b",
    re.IGNORECASE,
)


def _addresses_identity_question(response_text: str, active_npc_name: str) -> bool:
    return bool(active_npc_name) and _mentions(response_text, active_npc_name)


def _term_overlap(player_input: str, response_text: str) -> bool:
    terms = []
    for term in re.findall(r"\b\w{4,}\b", _normalized(player_input)):
        if term not in _SEARCH_STOP_WORDS and term not in terms:
            terms.append(term)
    if not terms:
        # Nothing meaningful to check overlap against (e.g. the whole
        # input was stopwords/short words) — silence, not a false
        # rejection, same principle Phase 19G already established.
        return True
    normalized_response = _normalized(response_text)
    return any(re.search(rf"\b{re.escape(term)}\w*\b", normalized_response) for term in terms)


def _gives_a_concrete_named_answer(response_text: str) -> bool:
    """Any proper noun at all (a name, place, or title) is a weak but
    real signal the NPC gave SOME specific answer rather than a vague
    non-response — used only to avoid rejecting a legitimate answer
    phrased without literally repeating the question's own words or the
    NPC's registered name (e.g. a nickname, or a place named instead)."""
    return bool(_proper_nouns(response_text))


def _strong_signal(
    subject: ConversationalSubject, player_input: str, response_text: str, active_npc_name: str, context: str
) -> bool | None:
    """True/False if a subject-specific, data-driven acceptance signal
    applies here; None if no such signal exists for this subject/context
    (caller falls through to the paraphrase-tolerant weak-signal check)."""
    if subject == ConversationalSubject.SELF_NAME:
        if not active_npc_name:
            return None
        return _addresses_identity_question(response_text, active_npc_name)
    if subject in _LOCATION_SUBJECTS:
        location_name = _private_location_fields(context).get("Name", "")
        if not location_name:
            return None
        return _mentions_canonical_name(response_text, location_name)
    if subject == ConversationalSubject.SERVICE:
        # Phase 24J.3 — confirmed via a real playtest: "tem alguma
        # estalagem que posso me hospedar?" answered with vague,
        # pleasant, on-topic-sounding praise of the settlement (no
        # mention of "estalagem" or the inn's own name at all) passed
        # the old weak-signal check anyway, because ANY proper noun
        # (here, the village's own already-known name) was accepted as
        # "gave a specific answer." An existence/availability question
        # about a service needs the specific SERVICE WORD the player
        # actually asked about (or its own canonical name/type-label) to
        # show up in the response — "claro, é um ótimo lugar" alone is
        # not actually answering "does one exist."
        service_match = _SERVICE_WORDS.search(player_input)
        if service_match is None:
            return None
        return _mentions(response_text, service_match.group(0))
    return None


def classify_relevance(
    player_input: str, response_text: str, active_npc_name: str = "", context: str = ""
) -> RelevanceOutcome:
    act = classify_conversational_act(player_input)
    if act not in _MUST_ADDRESS_ACTS:
        return RelevanceOutcome.ANSWERED

    normalized_response = _normalized(response_text)
    if _REFUSAL_MARKERS.search(normalized_response):
        return RelevanceOutcome.REFUSED
    if _CLARIFICATION_MARKERS.search(normalized_response):
        return RelevanceOutcome.REQUESTED_CLARIFICATION
    if _IGNORANCE_MARKERS.search(normalized_response):
        return RelevanceOutcome.ADMITTED_IGNORANCE
    if _EVASION_MARKERS.search(normalized_response):
        return RelevanceOutcome.EVADED

    subject = classify_subject(player_input)
    strong = _strong_signal(subject, player_input, response_text, active_npc_name, context)
    # Phase 24J.3 — an existence/availability question ("tem alguma
    # estalagem...?") must not be rescued by the generic weak signal:
    # "any proper noun at all" is exactly what let a real playtest
    # failure through before — a response that only names the ALREADY-
    # KNOWN settlement ("...conhecer os moradores de Eldor") contains a
    # proper noun, but never actually confirms, denies, or names the
    # service asked about. Every other must-address act still gets the
    # normal paraphrase-tolerant fallback.
    weak_signal = subject != ConversationalSubject.SERVICE and (
        _term_overlap(player_input, response_text) or _gives_a_concrete_named_answer(response_text)
    )

    if strong is True:
        return RelevanceOutcome.ANSWERED
    if strong is None:
        return RelevanceOutcome.ANSWERED if weak_signal else RelevanceOutcome.NOT_ADDRESSED
    # strong is False: the specific fact was demonstrably not given, but a
    # good-faith weak signal still counts as a plausible (if imperfect)
    # attempt rather than a flat non-response.
    return RelevanceOutcome.PLAUSIBLY_MISUNDERSTOOD if weak_signal else RelevanceOutcome.NOT_ADDRESSED


_NOT_ADDRESSED_MESSAGE = (
    "a resposta não demonstra nenhum reconhecimento do que o jogador perguntou/pediu; "
    "tópico completamente diferente sem recusa, evasão, pedido de esclarecimento ou "
    "admissão de desconhecimento explícitas — isso é deriva de tópico, não uma escolha "
    "intencional do NPC"
)


@register_validator
def validate_conversational_relevance(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    if not proposal.text.strip() or not claims:
        return []

    act = classify_conversational_act(proposal.player_input)
    if act not in _MUST_ADDRESS_ACTS:
        return []

    outcome = classify_relevance(
        proposal.player_input, proposal.text, proposal.active_npc_name or "", proposal.context
    )
    if outcome != RelevanceOutcome.NOT_ADDRESSED:
        return []

    # The whole response is off-topic, not just one sentence — every
    # claim index is marked so contract.py's repair drops the entire
    # text (falls under MIN_COHERENT_REPAIR_CHARS) rather than keeping
    # unrelated sentences the earlier claim was attached to.
    return [
        Violation(
            claim_index=claim.index,
            category=ClaimCategory.CONVERSATIONAL_RELEVANCE,
            reason=_NOT_ADDRESSED_MESSAGE,
        )
        for claim in claims
    ]
