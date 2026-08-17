from pathlib import Path
import re
from typing import Literal
import unicodedata

from app.ai.llm_service import LLMService
from app.core.logging import get_logger

logger = get_logger("narration")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "narrator_system.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

NarrationMode = Literal["OPENING", "CONTINUATION"]

_FORBIDDEN_STYLE_MARKERS = (
    "como se",
    "o ar parece",
    "o silêncio parece",
    "a sombra se alonga",
)

# Prepositions that put the protagonist's name in OBJECT position ("Osgar olhou
# para Logan"). Object position is fine — the world/NPC is still the subject.
_OBJECT_PREPOSITIONS = r"(?:para|a|ao|à|com|de|do|da|sobre|junto a)"

# Vocabulary that reveals awareness of being inside a game. NPCs believe the
# world is real and must never use these terms — only the narrator/system
# voice (outside NPC dialogue) may name the game or describe it as a game.
_META_GAME_TERMS = re.compile(
    r"\beverreach\b|\bjogador\w*\b|\blogout\b|\bsincroniza(?:cao|ção)\w*\b", re.IGNORECASE
)

# Verbs of speech that, followed by the protagonist's name, mean the narrator
# invented a NEW line of dialogue and attributed it to the protagonist.
_SPEECH_VERBS = (
    r"diz|disse|dizem|responde|respondeu|pergunta|perguntou|sussurra|sussurrou|"
    r"grita|gritou|exclama|exclamou|murmura|murmurou|resmunga|resmungou"
)

# Verbs describing an NPC/world reaction TO a decision already made — these
# presuppose the protagonist already replied, even when the reply itself never
# named them (e.g. an unattributed "— ..." line the narrator wrote and then
# treated as settled). Catches fabricated turns the name-based checks below miss.
_REACTS_TO_DECISION_VERBS = (
    r"respeita|aceita|concorda\s+com|reage\s+(?:a|à)|atende\s+(?:a|ao)|"
    r"acena\s+(?:a|para)|entende|compreende"
)
_DECISION_NOUNS = r"desejo|decis(?:ao|ão)|resposta|escolha|pedido|vontade"

_PERSISTENT_CONCEPTS = {
    "estrada": r"\bestradas?\b",
    "ponte": r"\bpontes?\b",
    "rio": r"\brios?\b",
    "riacho": r"\briachos?\b",
    "lago": r"\blagos?\b",
    "montanha": r"\bmontanhas?\b",
    "colina": r"\bcolinas?\b",
    "planície": r"\bplanicies?\b",
    "floresta": r"\bflorestas?\b",
    "bosque": r"\bbosques?\b",
    "templo": r"\btemplos?\b",
    "igreja": r"\bigrejas?\b",
    "capela": r"\bcapelas?\b",
    "guilda": r"\bguildas?\b",
    "castelo": r"\bcastelos?\b",
    "loja": r"\blojas?\b",
    "taverna": r"\btavernas?\b",
    "estalagem": r"\bestalagens?\b",
    "cidade": r"\bcidades?\b",
    "vila": r"\bvilas?\b",
    "ruína": r"\bruinas?\b",
    "masmorra": r"\b(masmorras?|dungeons?)\b",
    "facção": r"\bfacc(?:ao|oes)\b",
    "religião": r"\breligi(?:ao|oes)\b",
    "prática religiosa": r"\b(fe|religios[oa]s?|cult\w*|rez\w*|sacerd\w*|orac\w*)\b",
    "história inventada": r"\b(antepassad\w*|ancestr\w*)\b",
    "divindade": r"\b(deuses?|divindades?)\b",
    "dragão": r"\bdragoes?\b",
    "guerra": r"\bguerras?\b",
    "desastre": r"\bdesastres?\b",
    "norte": r"\bnorte\b",
    "sul": r"\bsul\b",
    "leste": r"\bleste\b",
    "oeste": r"\boeste\b",
}


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _authoritative_context_only(context: str) -> str:
    """Exclude the player's untrusted claim audit from the canon allow-list."""
    before_audit, marker, after_audit = context.partition("PLAYER INPUT CANON CHECK")
    if not marker:
        return context
    _audit, next_marker, authoritative_tail = after_audit.partition("\n\nACTIVE QUESTS")
    if not next_marker:
        return before_audit
    return f"{before_audit}\n\nACTIVE QUESTS{authoritative_tail}"


def _find_canon_violations(text: str, context: str, player_input: str) -> list[str]:
    """Detect claims that expand persistent world canon without support.

    These are the ONLY violations allowed to trigger the epistemic-refusal
    fallback ("— Não sei dizer.") — they concern objective, persistent facts
    about the world (geography, history, factions, structures...), not prose
    style or ordinary social conversation.
    """
    normalized_text = _normalized(text)
    normalized_context = _normalized(_authoritative_context_only(context))
    normalized_input = _normalized(player_input)
    violations = []
    for concept, pattern in _PERSISTENT_CONCEPTS.items():
        if not re.search(pattern, normalized_text) or re.search(pattern, normalized_context):
            continue
        came_from_player = re.search(pattern, normalized_input) is not None
        if came_from_player:
            denial_pattern = (
                rf"(nao\s+(ha|existe|conheco|sei)|nunca\s+(ouvi|vi)|desconheco)"
                rf".{{0,60}}{pattern}|{pattern}.{{0,60}}"
                rf"(nao\s+(conheco|sei)|nunca\s+(ouvi|vi)|desconheco)"
            )
            if re.search(denial_pattern, normalized_text):
                continue
        origin = "suposição do jogador" if came_from_player else "invenção da resposta"
        violations.append(
            f"conceito persistente não autorizado ({origin}): {concept!r}; "
            "pode apenas negar ou admitir desconhecimento, sem validá-lo nem acrescentar detalhes"
        )

    quantified_history = (
        r"\b(um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|vinte|trinta|"
        r"quarenta|cinquenta|sessenta|\d+)\s+anos?\b"
    )
    if re.search(quantified_history, normalized_text) and not re.search(
        quantified_history, normalized_context
    ):
        violations.append("biografia ou duração histórica quantificada sem fato canônico")
    if re.search(r"\b(alguns dizem|contam que|ouvi dizer|dizem que)\b", normalized_text) and "[rumor" not in normalized_context:
        violations.append("rumor atribuído a terceiros sem conhecimento RUMOR fornecido")
    invented_history = (
        r"\b(como a maioria|nao me lembro de quando|antigamente|naquela epoca|outrora)\b"
        r"|\bquando\b.{0,50}\bera\b"
        r"|\bantes\b.{0,80}\b(era|havia|existia|ficava|acontecia|faziam|jogavam)\b"
        r"|\bja foi\b"
        r"|\bvi\b.{0,60}\b(primeir\w*|virar\w*|crescer\w*)\b"
    )
    if re.search(invented_history, normalized_text) and not re.search(
        invented_history, normalized_context
    ):
        violations.append("passado histórico ou memória coletiva não fornecidos pelo cânone")

    weekday_history = r"\b(segunda|terca|quarta|quinta|sexta|sabado|domingo)(-feira)?\b"
    if re.search(weekday_history, normalized_text) and not re.search(
        weekday_history, normalized_context
    ):
        violations.append("costume ou calendário social não fornecido pelo cânone")

    for route_kind in ("estrada", "trilha", "ponte"):
        for direction in ("norte", "sul", "leste", "oeste", "nordeste", "noroeste", "sudeste", "sudoeste"):
            response_has_pair = any(
                re.search(rf"\b{route_kind}\w*\b", segment)
                and re.search(rf"\b{direction}\b", segment)
                for segment in re.split(r"[.\n]", normalized_text)
            )
            context_has_pair = any(
                re.search(rf"\b{route_kind}\w*\b", segment)
                and re.search(rf"\b{direction}\b", segment)
                for segment in normalized_context.splitlines()
            )
            if response_has_pair and not context_has_pair:
                violations.append(
                    f"combinação geográfica não registrada: {route_kind} + direção {direction}"
                )

    if "nothing about what exists beyond it" in normalized_context:
        word_count = len(re.findall(r"\b\w+\b", normalized_text))
        if word_count > 12:
            violations.append(
                "a resposta a uma lacuna explícita sobre o que existe além deve ser somente desconhecimento"
            )
    unsupported_terms = re.findall(
        r"- '([^']+)' appears only in the player's assumption", normalized_context
    )
    if unsupported_terms:
        word_count = len(re.findall(r"\b\w+\b", normalized_text))
        if word_count > 15:
            violations.append(
                "a resposta elaborou uma suposição do jogador marcada como ausente do cânone"
            )
    return violations


_AGENCY_VIOLATION_MESSAGE = (
    "a resposta usa o protagonista como personagem narrado; não escreva novas "
    "falas, gestos, ações ou reações para ele e mantenha mundo/NPCs como sujeitos"
)
_FABRICATED_TURN_MESSAGE = (
    "a resposta trata uma decisão, resposta ou desejo do protagonista como já "
    "manifestado, mas PLAYER INPUT não contém isso; não escreva o próximo turno do "
    "jogador nem a reação a ele, mesmo sem usar o nome do protagonista"
)

def _protagonist_agency_violations(
    text: str, character_name: str, mode: NarrationMode = "CONTINUATION"
) -> list[str]:
    """Detect the narrator inventing NEW actions/dialogue for the protagonist.

    Mentioning the protagonist's name is fine when the protagonist is merely
    the OBJECT of an NPC/world action ("Osgar olhou para Logan"). It is only a
    violation when the protagonist is made the SUBJECT of a new action/reaction,
    is given a new line of dialogue via attribution ("— ... — diz Logan"), or an
    NPC/the world reacts to a decision of theirs that was never actually made
    ("Talven respeita o desejo de Logan de tomar uma decisão" — even though
    nothing in PLAYER INPUT ever stated that desire).

    OPENING is intentionally strict as well: the narrator may describe the world
    and canonical scene state, but it must not assign even a neutral position,
    awakening, materialization, posture or first action to the protagonist unless
    that state/action is explicitly present in authoritative context.
    """
    if not character_name:
        return []
    name = re.escape(character_name)

    speaks_pattern = re.compile(rf"\b(?:{_SPEECH_VERBS})\s+{name}\b", re.IGNORECASE)
    if speaks_pattern.search(text):
        return [_AGENCY_VIOLATION_MESSAGE]

    reacts_pattern = re.compile(
        rf"\b(?:{_REACTS_TO_DECISION_VERBS})\b[^.\n]{{0,60}}\b(?:{_DECISION_NOUNS})\s+de\s+{name}\b",
        re.IGNORECASE,
    )
    if reacts_pattern.search(text):
        return [_FABRICATED_TURN_MESSAGE]

    subject_pattern = re.compile(rf"(?:^|[.\n—]\s*){name}\s+(?:se\s+)?(\w+)", re.IGNORECASE)
    for match in subject_pattern.finditer(text):
        preceding = text[max(0, match.start() - 20): match.start()]
        if re.search(rf"\b{_OBJECT_PREPOSITIONS}\s*$", preceding, re.IGNORECASE):
            continue
        return [_AGENCY_VIOLATION_MESSAGE]
    return []


def _extract_character_name(context: str) -> str:
    match = re.search(r"(?:^|\n)CURRENT PLAYER\nName: ([^\n(]+)", context)
    return match.group(1).strip() if match else ""


def _extract_active_npc_name(context: str) -> str:
    match = re.search(r"(?:^|\n)ACTIVE NPC CONTEXT\nName: ([^\n(]+)", context)
    return match.group(1).strip() if match else ""


def _find_style_violations(text: str) -> list[str]:
    """Detect cosmetic prose/format issues for diagnostics only.

    Style problems are deliberately NON-BLOCKING: they never trigger LLM
    regeneration, dropping content, or epistemic fallback. A slightly clumsy
    sentence is preferable to throwing away an otherwise valid grounded turn.
    """
    lowered = text.lower()
    violations = [
        f"expressão decorativa proibida: {marker!r}"
        for marker in _FORBIDDEN_STYLE_MARKERS
        if marker in lowered
    ]
    if '"' in text:
        violations.append("fala direta usa aspas em vez de travessão")

    paragraphs = [
        paragraph
        for paragraph in re.split(r"\n\s*\n", text.strip())
        if paragraph.strip()
    ]
    if len(paragraphs) > 3:
        violations.append("resposta desproporcional: use no máximo três parágrafos curtos")
    return violations


def _split_paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text.strip()) if paragraph.strip()]


def _split_sentences(paragraph: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", paragraph) if sentence.strip()]


def _is_dialogue_paragraph(paragraph: str) -> bool:
    return paragraph.strip().startswith(("—", "-"))


def _extract_simulated_player_names(context: str) -> list[str]:
    """Simulated players — unlike NPCs — may knowingly use game vocabulary
    (see the prompt's CONHECIMENTO DO MUNDO section), so a spoken line naming
    one of them is exempt from the meta-awareness check below."""
    match = re.search(r"(?:^|\n)VISIBLE PLAYERS\n((?:-.*\n?)*)", context)
    if not match:
        return []
    names = []
    for line in match.group(1).splitlines():
        entry = re.match(r"-\s*(.+?)\s*\(", line.strip())
        if entry:
            names.append(entry.group(1).strip())
    return names


def _paragraph_speaks_for_simulated_player(
    paragraphs: list[str], index: int, simulated_player_names: list[str]
) -> bool:
    """Whether the dialogue paragraph at `index` belongs to a simulated player —
    either because it names one directly, or because the narration beat right
    before it (if any) just introduced one as the speaker."""
    if not simulated_player_names:
        return False
    if any(_mentions(paragraphs[index], name) for name in simulated_player_names):
        return True
    if index > 0 and not _is_dialogue_paragraph(paragraphs[index - 1]):
        if any(_mentions(paragraphs[index - 1], name) for name in simulated_player_names):
            return True
    return False


def _npc_meta_awareness_violation(
    paragraphs: list[str], index: int, simulated_player_names: list[str]
) -> bool:
    """True if a DIALOGUE paragraph reveals awareness of being inside a game —
    checked at paragraph, not sentence, granularity, since only the FIRST
    sentence of a spoken turn carries the leading dash; later sentences in the
    same turn are still that speaker talking. Exempt if the line belongs to a
    simulated player, who is allowed to know this."""
    paragraph = paragraphs[index]
    if not _is_dialogue_paragraph(paragraph):
        return False
    if _META_GAME_TERMS.search(paragraph) is None:
        return False
    return not _paragraph_speaks_for_simulated_player(paragraphs, index, simulated_player_names)


def _find_meta_awareness_violations(text: str, simulated_player_names: list[str]) -> list[str]:
    paragraphs = _split_paragraphs(text)
    if any(
        _npc_meta_awareness_violation(paragraphs, index, simulated_player_names)
        for index in range(len(paragraphs))
    ):
        return [
            "um NPC revelou consciência de estar em um jogo em fala direta (nome do jogo, "
            "\"jogador\", \"logout\", \"sincronização\"...); NPCs acreditam que o mundo é "
            "real — só o narrador pode usar esses termos fora do diálogo, e jogadores "
            "simulados nomeados podem usá-los livremente"
        ]
    return []


def _drop_unsupported_segments(
    text: str, context: str, player_input: str, simulated_player_names: list[str] | None = None
) -> str:
    """Last-resort granular fallback: keep only the content that doesn't carry
    an unsupported canon claim or NPC meta-game awareness, instead of
    discarding the whole response. Meta-awareness drops the whole spoken turn
    (paragraph); canon claims are filtered sentence by sentence within it."""
    simulated_player_names = simulated_player_names or []
    paragraphs = _split_paragraphs(text)
    kept_paragraphs = []
    for index, paragraph in enumerate(paragraphs):
        if _npc_meta_awareness_violation(paragraphs, index, simulated_player_names):
            continue
        kept_sentences = [
            sentence
            for sentence in _split_sentences(paragraph)
            if not _find_canon_violations(sentence, context, player_input)
        ]
        if kept_sentences:
            kept_paragraphs.append(" ".join(kept_sentences))
    return "\n\n".join(kept_paragraphs).strip()


def _mentions(paragraph: str, name: str) -> bool:
    if not name:
        return False
    first_name = name.split()[0]
    return re.search(rf"\b{re.escape(first_name)}\b", paragraph, re.IGNORECASE) is not None


def _paragraph_attributed_speaker(paragraph: str, character_name: str, npc_name: str) -> str | None:
    """Who does a DIALOGUE paragraph explicitly establish as speaking, via a
    speech-verb adjacent to a name ("— ... — diz Osgar", "Osgar pergunta: — ...")?

    Deliberately stricter than a bare name search: a name appearing inside the
    dialogue text itself is often vocative address ("E você, senhor Osgar?"),
    not proof of who is speaking — treating it as attribution would let a
    fabricated player line that merely addresses the NPC by name slip through.
    """
    for name, label in ((npc_name, "npc"), (character_name, "player")):
        if not name:
            continue
        first = re.escape(name.split()[0])
        if re.search(rf"\b(?:{_SPEECH_VERBS})\s+{first}\b", paragraph, re.IGNORECASE):
            return label
        if re.search(rf"\b{first}\b\s*(?:,)?\s*(?:{_SPEECH_VERBS})\b", paragraph, re.IGNORECASE):
            return label
    return None


def _paragraph_establishes_speaker(paragraph: str, character_name: str, npc_name: str) -> str | None:
    """Who does this paragraph clearly establish as talking or about to talk —
    explicit attribution for a dialogue line, or simply being named as the
    actor in a narration beat (narration reliably names its own subject)."""
    if _is_dialogue_paragraph(paragraph):
        return _paragraph_attributed_speaker(paragraph, character_name, npc_name)
    if _mentions(paragraph, npc_name):
        return "npc"
    if _mentions(paragraph, character_name):
        return "player"
    return None


def _find_fabricated_turn_start(
    paragraphs: list[str], character_name: str, npc_name: str
) -> int | None:
    """Find where the narrator wrote the player's turn without ever naming them.

    The tell is the SHAPE: a dash-led line with no explicit speaker attribution
    (not the NPC's own continuing line, not the player's named line either).
    Two situations confirm it's the fabricated reply rather than the NPC's own
    uninterrupted monologue:
    - the narration beat right before it already frames the PLAYER as about to
      act/respond ("Logan sente-se... e responde") — that beat is itself the
      violation, and this dialogue line is its fabricated content; or
    - the NEXT paragraph explicitly re-establishes the NPC as speaking again —
      i.e. the NPC answering a line nobody in the scene actually said.
    A same-speaker monologue split across paragraphs has neither shape: the
    narration before it (if any) names the NPC, not the player, and nothing
    immediately after it re-introduces a speaker.
    """
    if not npc_name:
        return None
    for index, paragraph in enumerate(paragraphs):
        if not _is_dialogue_paragraph(paragraph):
            continue
        if _paragraph_attributed_speaker(paragraph, character_name, npc_name) is not None:
            continue  # explicitly attributed within the line itself

        prev_speaker = None
        if index > 0 and not _is_dialogue_paragraph(paragraphs[index - 1]):
            prev_speaker = _paragraph_establishes_speaker(paragraphs[index - 1], character_name, npc_name)

        if prev_speaker == "npc":
            continue  # legitimately attributed by the narration beat right before it
        if prev_speaker == "player":
            return index  # the narration already fabricated the player's turn

        if index + 1 < len(paragraphs):
            if _paragraph_establishes_speaker(paragraphs[index + 1], character_name, npc_name) == "npc":
                return index
    return None


def _fabricated_turn_violations(text: str, character_name: str, npc_name: str) -> list[str]:
    if not character_name:
        return []
    if _find_fabricated_turn_start(_split_paragraphs(text), character_name, npc_name) is not None:
        return [_FABRICATED_TURN_MESSAGE]
    return []


def _drop_agency_violations(
    text: str, character_name: str, npc_name: str = "", mode: NarrationMode = "CONTINUATION"
) -> str:
    """Remove fabricated protagonist dialogue/actions instead of accepting them.

    First truncates at the first fabricated player turn (see
    `_find_fabricated_turn_start`), then — within what's left — drops any
    sentence that still gives the protagonist a new line or reaction and
    everything after it in the same paragraph.
    """
    if not character_name:
        return text

    paragraphs = _split_paragraphs(text)
    fabricated_start = _find_fabricated_turn_start(paragraphs, character_name, npc_name)
    if fabricated_start is not None:
        paragraphs = paragraphs[:fabricated_start]

    kept_paragraphs = []
    for paragraph in paragraphs:
        kept_sentences = []
        for sentence in _split_sentences(paragraph):
            if _protagonist_agency_violations(sentence, character_name, mode):
                break
            kept_sentences.append(sentence)
        if kept_sentences:
            kept_paragraphs.append(" ".join(kept_sentences))
    return "\n\n".join(kept_paragraphs).strip()


def _safe_hard_failure_fallback(mode: NarrationMode, npc_name: str = "") -> str:
    """Return a deterministic response that cannot violate player agency or canon.

    This is only used when a hard violation survives revision and sanitization.
    It intentionally adds no location, history, route, item, quest, secret, or
    protagonist action. NPC silence / an uneventful beat are low-stakes scene
    behavior, not persistent worldbuilding.
    """
    if mode == "CONTINUATION" and npc_name:
        return f"{npc_name} permanece em silêncio."
    return "Nada acontece de imediato."


def narrate(
    llm_service: LLMService,
    mechanical_summary: str,
    context: str,
    player_input: str,
    recent_history: str,
    mode: NarrationMode = "CONTINUATION",
) -> str:
    """Render the next moment of a scene without changing authoritative game state.

    Validation is intentionally split into two classes:
    - HARD: canon, NPC meta-awareness, protagonist agency, fabricated player turns.
      These may trigger a limited rewrite and must never reach the player unresolved.
    - STYLE: cosmetic prose/format issues. These are logged only and never cause
      another LLM generation by themselves.
    """
    prompt = (
        f"MODO DA CENA:\n{mode}\n\n"
        f"SCENE CONTEXT:\n{context}\n\n"
        f"RECENT HISTORY:\n{recent_history}\n\n"
        f"PLAYER INPUT:\n{player_input}\n\n"
        "AUTHORITATIVE MECHANICAL FACTS:\n"
        f"{mechanical_summary}\n\n"
        "Escreva somente o próximo momento da cena, em português do Brasil."
    )

    logger.debug("NARRATOR SYSTEM PROMPT\n%s", _SYSTEM_PROMPT)
    logger.debug("SCENE CONTEXT\n%s", context)
    logger.debug("RECENT HISTORY\n%s", recent_history)
    logger.debug("PLAYER INPUT\n%s", player_input)
    logger.debug("AUTHORITATIVE FACTS\n%s", mechanical_summary)

    response = llm_service.generate(_SYSTEM_PROMPT, prompt)
    logger.debug("RAW NARRATOR RESPONSE\n%s", response)

    character_name = _extract_character_name(context)
    npc_name = _extract_active_npc_name(context)
    simulated_player_names = _extract_simulated_player_names(context)

    draft = response

    # Hard violations may request a rewrite. Two attempts are enough: repeated
    # regeneration often degrades a good local-model response and is expensive.
    # Style violations are NEVER included in the rewrite reasons.
    for attempt in range(1, 3):
        canon_violations = _find_canon_violations(draft, context, player_input)
        meta_violations = _find_meta_awareness_violations(draft, simulated_player_names)
        agency_violations = _protagonist_agency_violations(draft, character_name, mode)
        turn_violations = _fabricated_turn_violations(draft, character_name, npc_name)
        style_violations = _find_style_violations(draft)

        hard_violations = (
            canon_violations
            + meta_violations
            + agency_violations
            + turn_violations
        )

        logger.debug(
            "REVIEW RESULT (attempt %s)\nCANON VIOLATIONS: %s\nMETA-AWARENESS VIOLATIONS: %s\n"
            "AGENCY VIOLATIONS: %s\nFABRICATED TURN VIOLATIONS: %s\nSTYLE VIOLATIONS: %s",
            attempt,
            canon_violations,
            meta_violations,
            agency_violations,
            turn_violations,
            style_violations,
        )

        if not hard_violations:
            if style_violations:
                logger.warning(
                    "Narrator output contains non-blocking style issues (accepted without "
                    "regeneration): %s",
                    style_violations,
                )
            logger.debug("FINAL RESPONSE (accepted; no hard violations)\n%s", draft)
            return draft

        revision_prompt = (
            f"{prompt}\n\n"
            "DRAFT TO REVISE:\n"
            f"{draft}\n\n"
            "HARD VIOLATIONS TO REMOVE:\n- "
            + "\n- ".join(hard_violations)
            + "\n\nReescreva somente a narrativa corrigida, em no máximo dois parágrafos curtos. "
            "Corrija apenas as violações listadas. Preserve todo conteúdo válido do rascunho. "
            "Nunca dê novas ações, falas, pensamentos, sentimentos ou decisões ao protagonista. "
            "Preserve apenas acontecimentos sustentados pelo contexto. Para cada conceito "
            "persistente não autorizado, negue ou admita desconhecimento sem criar alternativa, "
            "equivalente, direção, segurança, história ou explicação. Não invente fatos para "
            "preencher a resposta."
        )
        logger.debug(
            "NARRATOR REVISION %s HARD REASONS\n%s",
            attempt,
            "\n".join(hard_violations),
        )
        draft = llm_service.generate(_SYSTEM_PROMPT, revision_prompt)
        logger.debug("RAW NARRATOR RESPONSE (REVISION %s)\n%s", attempt, draft)

    # From this point onward, no unresolved HARD violation is intentionally
    # returned to the player. Style remains non-blocking.
    remaining_style = _find_style_violations(draft)
    remaining_agency = _protagonist_agency_violations(draft, character_name, mode)
    remaining_turn = _fabricated_turn_violations(draft, character_name, npc_name)

    logger.debug(
        "REVIEW RESULT (final)\nAGENCY VIOLATIONS: %s\nFABRICATED TURN VIOLATIONS: %s\n"
        "STYLE VIOLATIONS: %s",
        remaining_agency,
        remaining_turn,
        remaining_style,
    )

    if remaining_style:
        logger.warning(
            "Narrator output still has non-blocking style issues after hard revisions: %s",
            remaining_style,
        )

    # Player agency is absolute. If the model still controls the protagonist,
    # deterministically remove those parts. Never knowingly return the flawed
    # draft merely because trimming would empty it.
    if remaining_agency or remaining_turn:
        trimmed = _drop_agency_violations(draft, character_name, npc_name, mode)
        if trimmed:
            logger.warning(
                "FALLBACK REASON: protagonist still had fabricated dialogue/actions after "
                "hard revisions; offending content was dropped: %s\nKEPT:\n%s",
                remaining_agency + remaining_turn,
                trimmed,
            )
            draft = trimmed
        else:
            safe = _safe_hard_failure_fallback(mode, npc_name)
            logger.error(
                "FALLBACK REASON: protagonist agency violation could not be removed without "
                "emptying the response. Returning deterministic safe fallback instead of the "
                "known-invalid draft: %s\nFALLBACK:\n%s",
                remaining_agency + remaining_turn,
                safe,
            )
            return safe

    remaining_canon = (
        _find_canon_violations(draft, context, player_input)
        + _find_meta_awareness_violations(draft, simulated_player_names)
    )
    logger.debug("REVIEW RESULT (post-agency-trim)\nCANON VIOLATIONS: %s", remaining_canon)

    if not remaining_canon:
        logger.debug("FINAL RESPONSE\n%s", draft)
        return draft

    logger.warning("Narrator output still violates canon after hard revisions: %s", remaining_canon)

    # Granular filtering is the preferred canon fallback: preserve supported
    # dialogue/reaction and remove only the unsupported claim(s).
    filtered = _drop_unsupported_segments(
        draft,
        context,
        player_input,
        simulated_player_names,
    )

    # The filter removes canon/meta claims but should not be allowed to leak an
    # agency violation that survived due to sentence reshaping. Recheck once.
    if filtered:
        filtered_agency = _protagonist_agency_violations(filtered, character_name, mode)
        filtered_turn = _fabricated_turn_violations(filtered, character_name, npc_name)
        if filtered_agency or filtered_turn:
            filtered = _drop_agency_violations(filtered, character_name, npc_name, mode)

    if filtered:
        logger.warning(
            "FALLBACK REASON: dropped unsupported canon/meta segments and kept the supported "
            "remainder\n%s",
            filtered,
        )
        logger.debug("FINAL RESPONSE (granular fallback)\n%s", filtered)
        return filtered

    # Only an active NPC answering a factual gap gets the epistemic refusal.
    # OPENING/no-NPC contexts use a neutral deterministic beat instead; we never
    # return a draft that is already known to violate canon.
    if mode == "CONTINUATION" and npc_name:
        logger.warning(
            "FALLBACK REASON: no supported segment survived canon filtering with an active NPC; "
            "using epistemic refusal"
        )
        logger.debug("FINAL RESPONSE (epistemic fallback)\n— Não sei dizer.")
        return "— Não sei dizer."

    safe = _safe_hard_failure_fallback(mode, npc_name)
    logger.error(
        "FALLBACK REASON: no supported segment survived canon filtering and there is no active "
        "NPC for an epistemic refusal. Returning deterministic safe fallback instead of the "
        "known-invalid draft.\nFALLBACK:\n%s",
        safe,
    )
    return safe