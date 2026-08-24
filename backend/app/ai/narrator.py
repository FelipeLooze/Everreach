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

_OPENING_ALLOWED_SUBJECT_VERBS = {
    "esta",
    "encontra",
    "surge",
    "aparece",
    "materializa",
}

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
    r"\b(?:vrmmorpg|vrmmo|logout|login|servidor|npc)\b|"
    r"\bsincroniza(?:cao|ção)\w*\b|"
    r"\b(?:sou|somos|sao|são)\s+(?:um\s+|uns\s+)?jogador(?:es)?\b",
    re.IGNORECASE,
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
    "casa": r"\bcasas?\b",
    "madeira": r"\bmadeira\b",
    "sapé": r"\bsape\b",
    "ferramenta": r"\bferramentas?\b",
    "artesanato": r"\bartesanato\b",
    "recursos naturais": r"\brecursos?\s+naturais\b",
    "profissões locais": r"\b(fazendeir\w*|mineir\w*|artesaos?|artesa)\b",
    "animais selvagens": r"\banimais?\s+selvagens?\b",
    "segurança de rota": r"\b(segur[oa]s?|perigos[oa]s?)\b",
    "trilha": r"\btrilhas?\b",
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

_UNSOLICITED_OPENING_INTERACTION_MESSAGE = (
    "a abertura iniciou diálogo ou aproximação de um habitante sem uma interação "
    "ativa autorizada; apresente apenas a situação inicial e devolva o controle ao jogador"
)
_HIDDEN_NAME_MESSAGE = (
    "a resposta revelou um nome canônico que o protagonista ainda não conhece e que "
    "nenhum interlocutor ativo estava autorizado a comunicar"
)


_PROMPT_LEAK_MARKERS = (
    "HARD VIOLATIONS TO REMOVE",
    "VIOLATIONS TO REMOVE",
    "DRAFT TO REVISE",
    "SCENE CONTEXT:",
    "RECENT HISTORY:",
    "PLAYER INPUT:",
    "AUTHORITATIVE MECHANICAL FACTS:",
    "MODO DA CENA:",
    "Reescreva somente a narrativa corrigida",
    "Escreva somente o próximo momento da cena",
    # Not a literal prompt echo — the model regressing into simulating a
    # whole future exchange itself, inventing several more player/NPC
    # turns nobody asked for, labeled with its own shorthand for the
    # "PLAYER INPUT:"/narrator-response shape it has seen in the prompt.
    # Just as unacceptable as an echoed instruction: everything from the
    # first such label onward is fabricated, unauthorized turns.
    "PLAYER:",
    "NARRATOR:",
    # Phase 24A.1 — the new bounded history/current-turn framing's own
    # literal headers/footers. If the model ever echoes one of these
    # back, that is unambiguously leaked scaffolding, never real prose.
    "HISTÓRICO DE TROCAS RECENTES",
    "FIM DO HISTÓRICO DE TROCAS RECENTES",
    "TURNO ATUAL DO JOGADOR",
    "FIM DO TURNO ATUAL DO JOGADOR",
)


def _strip_prompt_leak(text: str) -> str:
    """If the model echoed part of its own prompt/instructions instead of (or
    appended to) actual narrative, cut everything from the first leaked marker
    onward. Under a long revision prompt, a local model sometimes regresses to
    parroting its input verbatim — that scaffolding text must never reach the
    player, even when it contains no canon/agency violation on its own."""
    earliest = len(text)
    for marker in _PROMPT_LEAK_MARKERS:
        index = text.find(marker)
        if index != -1:
            earliest = min(earliest, index)
    return text[:earliest].strip()


_EMPTY_OR_LEAKED_RESPONSE_MESSAGE = (
    "a resposta ficou vazia depois de remover texto de instrução/prompt ecoado pelo "
    "modelo; escreva somente a cena em português, nunca repita estas instruções"
)


def _empty_response_violations(text: str) -> list[str]:
    if not text.strip():
        return [_EMPTY_OR_LEAKED_RESPONSE_MESSAGE]
    return []


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


_COMBAT_ACTION_VERBS = (
    r"ataca(?:m|ndo)?|atacou|atacaram|golpeia(?:m|ndo)?|golpeou|golpearam|"
    r"acerta(?:m|ndo)?|acertou|acertaram|erra(?:m|ndo)?|errou|erraram|"
    r"fere(?:m)?|feriu|feriram|fere?indo|"
    r"defende(?:m|ndo)?|defendeu|defenderam|"
    r"interv[ée]m|intervindo|intervieram|"
    r"luta(?:m|ndo)?|lutou|lutaram|"
    r"saca(?:m|ndo)?|sacou|sacaram|"
    r"empunha(?:m|ndo)?|empunhou|empunharam"
)


def _unauthorized_combatant_message(name: str) -> str:
    return (
        f"'{name}' age como combatente (ataca, defende ou intervém fisicamente na luta) "
        "sem constar em ACTIVE COMBAT PARTICIPANTS; NPCs apenas visíveis na cena são "
        "espectadores e nunca entram em combate por conta da narrativa"
    )


def _visible_npc_names(context: str) -> list[str]:
    match = re.search(r"(?:^|\n)VISIBLE NPCS\n((?:-.*\n?)*)", context)
    if not match:
        return []
    names = []
    for line in match.group(1).splitlines():
        entry = re.match(r"-\s*(.+?)\s*\(", line.strip())
        if entry:
            names.append(entry.group(1).strip())
    return names


def _combat_participant_names(context: str) -> set[str] | None:
    """Names authorized to fight this turn, or None when no combat is active."""
    match = re.search(r"(?:^|\n)ACTIVE COMBAT PARTICIPANTS\n((?:-.*\n?)*)", context)
    if not match:
        return None
    names = set()
    for line in match.group(1).splitlines():
        entry = re.match(r"-\s*(.+?)\s*\(", line.strip())
        if entry:
            names.add(entry.group(1).strip())
    return names


def _find_unauthorized_combatant_violations(text: str, context: str) -> list[str]:
    """Flag a bystander NPC (visible but not an ACTIVE COMBAT PARTICIPANT)
    written as taking a combat action — e.g. a local jumping in to help.

    Only checked while combat is actually active (participant list present);
    outside combat any NPC may act freely."""
    participants = _combat_participant_names(context)
    if participants is None:
        return []
    normalized_text = _normalized(text)
    for name in _visible_npc_names(context):
        if name in participants:
            continue
        first = re.escape(_normalized(name.split()[0]))
        if re.search(rf"\b{first}\b[^.\n]{{0,40}}?\b(?:{_COMBAT_ACTION_VERBS})\b", normalized_text):
            return [_unauthorized_combatant_message(name)]
    return []


def _drop_unauthorized_combatant_segments(text: str, context: str) -> str:
    """Granular fallback: remove only the paragraph(s) giving a bystander NPC
    combat agency, preserving the rest of the (otherwise valid) narration."""
    paragraphs = _split_paragraphs(text)
    kept_paragraphs = [
        paragraph
        for paragraph in paragraphs
        if not _find_unauthorized_combatant_violations(paragraph, context)
    ]
    return "\n\n".join(kept_paragraphs).strip()


# Verbs that legitimately bring a bystander NPC into an ongoing conversation —
# only after one of these narrates them arriving may they be voiced at all.
_NPC_ENTRANCE_VERBS = re.compile(
    r"\b(?:chega(?:m)?|chegou|chegaram|entra(?:m)?|entrou|entraram|"
    r"aparece(?:m)?|apareceu|apareceram|surge(?:m)?|surgiu|surgiram|"
    r"aproxima(?:m)?(?:-se)?|aproximou-se|aproximaram-se|"
    r"interrompe(?:m)?|interrompeu|interromperam|"
    r"junta(?:m)?-se|juntou-se|juntaram-se)\b",
    re.IGNORECASE,
)


def _unauthorized_speaker_message(name: str) -> str:
    if name == _UNRESOLVED_TURN_SENTINEL:
        return (
            "a resposta narra mais de uma fala/turno de diálogo sem interlocutor "
            "autorizado; escreva no máximo a primeira fala de quem se aproxima e "
            "pare — não invente uma troca inteira, nem uma resposta do protagonista, "
            "sem que o jogador tenha escrito outra ação"
        )
    return (
        f"'{name}' recebe fala atribuída sem ser o interlocutor ativo nem ter sido "
        "apresentado entrando na cena; um NPC apenas visível é espectador — só pode "
        "falar depois de uma cena explícita de chegada/aproximação/interrupção"
    )


_QUOTE_MARK = re.compile(r'["“]')


_COLON_THEN_DASH_QUOTE = re.compile(r":\s*—")


def _paragraph_has_spoken_dialogue(paragraph: str) -> bool:
    """True for a quote-mark paragraph ("Nome disse, '...'") OR the
    dash-led screenplay style this codebase's own dialogue convention
    actually uses ("— fala — verbo") — _is_dialogue_paragraph already
    recognizes the dash-prefixed and colon-attributed shapes; this adds
    the inline-quote-mark shape _paragraph_speaker_among's stricter
    patterns miss, and a colon-then-dash mid-paragraph ("... e
    responde: — Meu nome é Lena.") — a real, fulfilled reply, not the
    dangling-promise shape _find_unfulfilled_speech_promise_violations
    exists to catch, which _is_dialogue_paragraph alone would miss
    since it only recognizes a dash that OPENS the paragraph."""
    return (
        _is_dialogue_paragraph(paragraph)
        or bool(_QUOTE_MARK.search(paragraph))
        or bool(_COLON_THEN_DASH_QUOTE.search(paragraph))
    )


_SPEECH_PROMISE_PARAGRAPH = re.compile(
    rf"\b(?:{_SPEECH_VERBS}|inclina(?:-se)?|estende|aponta|debru[çc]a(?:-se)?)\b[^.\n]*:",
    re.IGNORECASE,
)
_UNFULFILLED_SPEECH_PROMISE_MESSAGE = (
    "a resposta promete uma fala ('responde:', 'inclina-se... :', etc.) "
    "mas nunca a entrega em lugar nenhum do texto; ou complete a fala prometida "
    "imediatamente, ou reescreva sem prometer uma fala que não vai vir"
)


def _find_unfulfilled_speech_promise_violations(text: str) -> list[str]:
    """A distinct local-model failure mode from an outright empty response:
    the draft narrates right up to the edge of an NPC's line — "... e
    responde:", "Ela se inclina... com um ar confidencial:" — and then
    never actually delivers it anywhere in the draft. The colon-promise
    doesn't have to be the very end of its paragraph — the model just as
    often keeps narrating past it in the same paragraph (more scene-
    setting prose, never the promised line) as it does leaving it fully
    dangling at the end, sometimes across several such promises in a
    row, leaving the player's direct question (often one
    with no obvious canned answer, like the NPC's own name) completely
    unanswered while reading as if a reply were coming. Only fires when
    NO paragraph in the whole draft has any spoken dialogue at all — a
    real reply anywhere after the promise means it was fulfilled."""
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []
    if any(_paragraph_has_spoken_dialogue(paragraph) for paragraph in paragraphs):
        return []
    if any(_SPEECH_PROMISE_PARAGRAPH.search(paragraph.strip()) for paragraph in paragraphs):
        return [_UNFULFILLED_SPEECH_PROMISE_MESSAGE]
    return []


def _single_unattributed_quoted_speaker(paragraph: str, visible_npcs: list[str]) -> str | None:
    """Fallback for real dialogue this local model writes in a shape
    _paragraph_speaker_among's stricter patterns don't recognize — e.g.
    "Aldric Draven assente, ... 'Sim, temos...'", where the speech verb
    ("assente") isn't in _SPEECH_VERBS and isn't adjacent to the name.
    Deliberately narrow: only fires when the paragraph actually contains
    spoken dialogue AND exactly one visible NPC's name appears in it at
    all — an ambiguous multi-name paragraph is left to the stricter
    checks rather than guessed at, same caution as every other Phase 19
    validator."""
    if not _paragraph_has_spoken_dialogue(paragraph):
        return None
    mentioned = [
        name
        for name in visible_npcs
        if name and re.search(rf"\b{re.escape(name.split()[0])}\b", paragraph)
    ]
    return mentioned[0] if len(mentioned) == 1 else None


_UNRESOLVED_TURN_SENTINEL = "(diálogo adicional não atribuível)"


def _scan_unauthorized_speakers(
    paragraphs: list[str], visible_npcs: list[str], active_interlocutor_name: str
):
    """Yield (paragraph, unauthorized_speaker) for each paragraph, tracking NPC
    entrances as they're narrated so a later paragraph may legitimately voice
    an NPC who was just explicitly introduced joining the scene.

    When no interlocutor was ever mechanically authorized (the multi-NPC
    ambiguity case — see engine._handle_talk), a scene may still
    legitimately OPEN with one NPC's unattributed greeting/offer (nobody
    has been resolved as a target yet, but someone approaching and
    speaking first is normal). What is never legitimate is a SECOND
    quoted exchange nobody can be named for in the same draft — that is
    the model writing a whole back-and-forth (routinely including a
    fabricated protagonist reply attributed only by pronoun, "admitiu
    ele"/"disse ela", a shape none of the name-based checks recognize)
    with no player input driving the later turns. So exactly one
    unattributable quoted paragraph is tolerated per draft; any further
    one is flagged, regardless of whose voice it's meant to be.
    """
    authorized = {active_interlocutor_name} if active_interlocutor_name else set()
    # The budget rule below only ever applies with NO active interlocutor.
    # When one exists, an unresolved speaker on a dialogue paragraph is
    # assumed to be them continuing (unattributed follow-up paragraphs
    # from the same ongoing speaker are normal prose, not a new turn) —
    # exactly the pre-existing behavior, unchanged here.
    unattributed_quote_budget = 1
    for paragraph in paragraphs:
        if not _is_dialogue_paragraph(paragraph):
            normalized = _normalized(paragraph)
            for name in visible_npcs:
                if name in authorized:
                    continue
                first = re.escape(_normalized(name.split()[0]))
                if re.search(rf"\b{first}\b", normalized) and _NPC_ENTRANCE_VERBS.search(normalized):
                    authorized.add(name)
            speaker = _single_unattributed_quoted_speaker(paragraph, visible_npcs)
            if speaker is None and not active_interlocutor_name and _QUOTE_MARK.search(paragraph):
                if unattributed_quote_budget > 0:
                    unattributed_quote_budget -= 1
                else:
                    yield paragraph, _UNRESOLVED_TURN_SENTINEL
                    continue
            yield paragraph, (speaker if speaker and speaker not in authorized else None)
            continue
        speaker = _paragraph_speaker_among(paragraph, visible_npcs)
        if speaker is None:
            speaker = _single_unattributed_quoted_speaker(paragraph, visible_npcs)
        if speaker is None and not active_interlocutor_name:
            if unattributed_quote_budget > 0:
                unattributed_quote_budget -= 1
            else:
                yield paragraph, _UNRESOLVED_TURN_SENTINEL
                continue
        yield paragraph, (speaker if speaker and speaker not in authorized else None)


def _find_unauthorized_speaker_violations(
    text: str, context: str, active_interlocutor_name: str
) -> list[str]:
    """Only the active interlocutor may be given attributed dialogue. A
    different NPC merely visible in the scene is a bystander and may speak
    only once explicitly narrated joining the conversation."""
    visible_npcs = _visible_npc_names(context)
    if not visible_npcs:
        return []
    for _, unauthorized in _scan_unauthorized_speakers(
        _split_paragraphs(text), visible_npcs, active_interlocutor_name
    ):
        if unauthorized:
            return [_unauthorized_speaker_message(unauthorized)]
    return []


def _drop_unauthorized_speaker_segments(
    text: str, context: str, active_interlocutor_name: str
) -> str:
    """Granular fallback: remove only the paragraph(s) giving a bystander NPC
    unauthorized dialogue, preserving the rest of the narration."""
    visible_npcs = _visible_npc_names(context)
    kept_paragraphs = [
        paragraph
        for paragraph, unauthorized in _scan_unauthorized_speakers(
            _split_paragraphs(text), visible_npcs, active_interlocutor_name
        )
        if not unauthorized
    ]
    return "\n\n".join(kept_paragraphs).strip()


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

    for paragraph in _split_paragraphs(text):
        colon_speaker = _colon_dialogue_speaker(paragraph)
        if colon_speaker is not None and _mentions(colon_speaker, character_name):
            return [_AGENCY_VIOLATION_MESSAGE]

    speaks_pattern = re.compile(rf"\b(?:{_SPEECH_VERBS})\s+{name}\b", re.IGNORECASE)
    if speaks_pattern.search(text):
        return [_AGENCY_VIOLATION_MESSAGE]

    # Phase 24A.1 — the spec's own explicit forbidden examples ("Logan
    # thinks the man is lying", "Logan feels relieved", "Logan decides
    # to run", "Logan agrees") use an interpreted mental-state verb, not
    # a speech verb — speaks_pattern above never matches "pensa"/"sente"/
    # "acha"/"decide"/"concorda". "{name} pensa..." (name leading a
    # clause) is already caught by subject_pattern below regardless of
    # verb; this specifically covers the verb-first Portuguese word
    # order ("pensa Logan, satisfeito.") that subject_pattern's
    # name-must-lead-the-clause anchor cannot — confirmed missing by a
    # real regression test built from actual observed output. Deliberately
    # excludes "percebe"/"nota" (notices) — those are legitimately
    # sensory/perceptual in this codebase's own established SENSATION
    # != EMOTION policy (19E) and would false-positive on allowed
    # physical-perception narration.
    mental_state_pattern = re.compile(
        rf"\b(?:pensa|pensou|sente|sentiu|acha|achou|decide|decidiu|concorda|concordou)\s+{name}\b",
        re.IGNORECASE,
    )
    if mental_state_pattern.search(text):
        return [_AGENCY_VIOLATION_MESSAGE]

    # A fabricated protagonist reply doesn't always carry an explicit
    # "— ... — diz Logan" attribution the checks above look for — this
    # local model commonly writes it as a plain unattributed dialogue
    # line that self-identifies in first person instead ("— Eu... Sou
    # Logan, se alguém..."), especially answering an NPC's own direct
    # question. That self-identification alone is unambiguous regardless
    # of whether any NPC name is known yet (a first-contact scene has
    # none), so this check runs unconditionally, unlike the npc_name-
    # gated fabricated-turn checks below.
    self_identifies_pattern = re.compile(
        rf"\b(?:sou|eu\s+sou|meu\s+nome\s+[ée])\s+(?:o\s+|a\s+)?{name}\b",
        re.IGNORECASE,
    )
    if self_identifies_pattern.search(text):
        return [_AGENCY_VIOLATION_MESSAGE]

    reacts_pattern = re.compile(
        rf"\b(?:{_REACTS_TO_DECISION_VERBS})\b[^.\n]{{0,60}}\b(?:{_DECISION_NOUNS})\s+de\s+{name}\b",
        re.IGNORECASE,
    )
    if reacts_pattern.search(text):
        return [_FABRICATED_TURN_MESSAGE]

    # Tolerate a short comma-bounded appositive between the name and the verb
    # ("Filipe, ofegante, tenta...") — otherwise it breaks the match entirely
    # and lets a fabricated action/dialogue slip through right after it.
    subject_pattern = re.compile(
        rf"(?:^|[.\n—]\s*){name}\b(?:\s*,[^.\n]{{0,60}}?,)?\s+(?:se\s+)?(\w+)",
        re.IGNORECASE,
    )

    for match in subject_pattern.finditer(text):
        preceding = text[max(0, match.start() - 20): match.start()]

        if re.search(rf"\b{_OBJECT_PREPOSITIONS}\s*$", preceding, re.IGNORECASE):
            continue

        verb = _normalized(match.group(1))

        # During OPENING the protagonist may be the grammatical subject only
        # for the involuntary physical result of the transportation.
        if mode == "OPENING" and verb in _OPENING_ALLOWED_SUBJECT_VERBS:
            continue

        return [_AGENCY_VIOLATION_MESSAGE]
    return []


def _extract_character_name(context: str) -> str:
    match = re.search(r"(?:^|\n)CURRENT PLAYER\nName: ([^\n(]+)", context)
    return match.group(1).strip() if match else ""


def _extract_active_npc_name(context: str) -> str:
    match = re.search(r"(?:^|\n)ACTIVE NPC CONTEXT\nName: ([^\n(]+)", context)
    return match.group(1).strip() if match else ""


def _extract_active_transported_person_name(
    context: str,
) -> str:
    match = re.search(
        r"(?:^|\n)ACTIVE TRANSPORTED PERSON CONTEXT\n"
        r"Name: ([^\n(]+)",
        context,
    )

    return (
        match.group(1).strip()
        if match
        else ""
    )


def _extract_active_interlocutor_name(
    context: str,
) -> str:
    return (
        _extract_active_npc_name(context)
        or _extract_active_transported_person_name(
            context
        )
    )


def _private_location_fields(context: str) -> dict[str, str]:
    section_match = re.search(
        r"CANONICAL LOCATION CONTEXT[^\n]*\n(.*?)(?:\n\n|\Z)",
        context,
        re.DOTALL,
    )
    if not section_match:
        return {}
    fields = {}
    for label in ("Name", "Region"):
        match = re.search(rf"^{label}:\s*([^\n]+)", section_match.group(1), re.MULTILINE)
        if match and match.group(1).strip().lower() != "unknown":
            fields[label] = match.group(1).strip()
    return fields


def _npc_knowledge(context: str) -> str:
    match = re.search(
        r"(?:^|\n)NPC KNOWLEDGE\n(.*?)(?:\n\nPLAYER KNOWLEDGE|\Z)",
        context,
        re.DOTALL,
    )
    return match.group(1) if match else ""


def _find_hidden_name_violations(
    text: str, context: str, active_interlocutor_name: str
) -> list[str]:
    """Private canonical metadata is not automatically narrator-visible truth.

    Without an active interlocutor capable of communicating it, a location or
    region whose knowledge flag is NO must not appear in the prose merely
    because its private database name was included in the context.
    """
    private_fields = _private_location_fields(context)
    npc_knowledge = _npc_knowledge(context)
    unknown_names = []
    for kind, field in (("location", "Name"), ("region", "Region")):
        flag = re.search(
            rf"Current {kind} canonical name known to player:\s*NO",
            context,
            re.IGNORECASE,
        )
        name = private_fields.get(field)
        if not flag or not name or not _mentions(text, name):
            continue
        npc_can_reveal = active_interlocutor_name and _mentions(npc_knowledge, name)
        if not npc_can_reveal:
            unknown_names.append(name)
    if unknown_names:
        return [_HIDDEN_NAME_MESSAGE]
    return []


def _drop_hidden_name_segments(
    text: str, context: str, active_interlocutor_name: str
) -> str:
    """Granular fallback: remove only the paragraph(s) that leak a canonical
    name the player doesn't know, preserving the rest of the narration."""
    paragraphs = _split_paragraphs(text)
    kept_paragraphs = [
        paragraph
        for paragraph in paragraphs
        if not _find_hidden_name_violations(paragraph, context, active_interlocutor_name)
    ]
    return "\n\n".join(kept_paragraphs).strip()


def _find_unsolicited_opening_interaction_violations(
    text: str,
    mode: NarrationMode,
    active_interlocutor_name: str,
    simulated_player_names: list[str],
) -> list[str]:
    if mode != "OPENING" or active_interlocutor_name:
        return []
    paragraphs = _split_paragraphs(text)
    native_dialogue = any(
        _is_dialogue_paragraph(paragraph)
        and not _paragraph_speaks_for_simulated_player(
            paragraphs, index, simulated_player_names
        )
        for index, paragraph in enumerate(paragraphs)
    )
    native_approach = any(
        re.search(
            r"\b(?:se\s+aproxima|aproxima-se|vem\s+ate|dirige-se\s+a)\b",
            _normalized(paragraph),
        )
        and not any(_mentions(paragraph, name) for name in simulated_player_names)
        for paragraph in paragraphs
    )
    if native_dialogue or native_approach:
        return [_UNSOLICITED_OPENING_INTERACTION_MESSAGE]
    return []


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


# A local model sometimes writes dialogue in screenplay style ('Nome: "..."')
# instead of the expected em-dash convention. Both must be recognized as
# dialogue, or every dialogue-aware check below silently misses this format.
_COLON_DIALOGUE_ATTRIBUTION = re.compile(
    r"^([A-ZÀ-Ý][\wÀ-ÿ'’]{1,40}(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'’]{1,40}){0,2})\s*:\s*(?=[\"“—-])"
)


def _colon_dialogue_speaker(paragraph: str) -> str | None:
    match = _COLON_DIALOGUE_ATTRIBUTION.match(paragraph.strip())
    return match.group(1).strip() if match else None


def _is_dialogue_paragraph(paragraph: str) -> bool:
    stripped = paragraph.strip()
    return stripped.startswith(("—", "-")) or _colon_dialogue_speaker(paragraph) is not None


def _extract_simulated_player_names(
    context: str,
) -> list[str]:
    """
    Return the names of transported people relevant to the scene.

    The active transported interlocutor is included even if the visible
    list is absent or truncated.
    """

    names = []

    active_name = (
        _extract_active_transported_person_name(
            context
        )
    )

    if active_name:
        names.append(active_name)

    match = re.search(
        r"(?:^|\n)"
        r"(?:VISIBLE TRANSPORTED PEOPLE|VISIBLE PLAYERS)"
        r"\n((?:-.*\n?)*)",
        context,
    )

    if not match:
        return names

    for line in match.group(1).splitlines():
        entry = re.match(
            r"-\s*(.+?)\s*\(",
            line.strip(),
        )

        if not entry:
            continue

        name = entry.group(1).strip()

        if name not in names:
            names.append(name)

    return names


def _paragraph_speaks_for_simulated_player(
    paragraphs: list[str], index: int, simulated_player_names: list[str]
) -> bool:
    """Whether the dialogue paragraph at `index` belongs to a transported person. —
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
            "um habitante nativo usou conhecimento tecnológico ou de videogame incompatível "
            "com seu contexto; habitantes nativos não sabem que Everreach é um jogo porque "
            "Everreach não é um jogo. Pessoas transportadas podem conhecer esse vocabulário "
            "por sua vida anterior, mas isso não torna o mundo uma simulação"
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


def _paragraph_speaker_among(paragraph: str, candidates: list[str]) -> str | None:
    """Which of these candidate names (if any) does this paragraph explicitly
    establish as speaking — via 'Nome: "..."' screenplay attribution, or a
    speech-verb adjacent to a name ("— ... — diz Osgar", "Osgar pergunta: — ...")?

    Deliberately stricter than a bare name search: a name appearing inside the
    dialogue text itself is often vocative address ("E você, senhor Osgar?"),
    not proof of who is speaking — treating it as attribution would let a
    fabricated player line that merely addresses someone by name slip through.
    """
    colon_speaker = _colon_dialogue_speaker(paragraph)
    if colon_speaker is not None:
        for name in candidates:
            if name and _mentions(colon_speaker, name):
                return name
        return None
    for name in candidates:
        if not name:
            continue
        first = re.escape(name.split()[0])
        if re.search(rf"\b(?:{_SPEECH_VERBS})\s+{first}\b", paragraph, re.IGNORECASE):
            return name
        if re.search(rf"\b{first}\b\s*(?:,)?\s*(?:{_SPEECH_VERBS})\b", paragraph, re.IGNORECASE):
            return name
    return None


def _paragraph_attributed_speaker(paragraph: str, character_name: str, npc_name: str) -> str | None:
    speaker = _paragraph_speaker_among(paragraph, [npc_name, character_name])
    if speaker is None:
        return None
    return "npc" if speaker == npc_name else "player"


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

        # A line that addresses the active NPC and speaks in the first person
        # cannot be that NPC's own continuation. Local models commonly insert
        # exactly this shape after a LOOK action: "— Obrigado, senhor. O que me
        # aconselha?", then continue by making the NPC answer it.
        normalized_paragraph = _normalized(paragraph)
        addresses_npc = re.search(
            r"\b(?:senhor|senhora|seu|dona)\b",
            normalized_paragraph,
        ) or (
            npc_name
            and re.search(
                rf"(?:^|[,;])\s*{re.escape(_normalized(npc_name.split()[0]))}\b",
                normalized_paragraph,
            )
        )
        first_person = re.search(
            r"\b(?:eu|me|meu|minha|vou|posso|preciso|agradeco|aconselha)\b",
            normalized_paragraph,
        )
        if addresses_npc and first_person:
            return index

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


_QUESTION_WORDS = re.compile(
    r"\b(qual|quais|quem|onde|como|quando|por\s*que|porque|quanto|quantos|quantas)\b",
    re.IGNORECASE,
)


def _looks_like_direct_question(player_input: str) -> bool:
    """Deterministic, cheap heuristic — Phase 24A.1 explicitly defers a
    real conversational-act classifier (Phase 24E/24J) to later Phase 24
    work; this only needs to catch the obvious case ("?" or a Portuguese
    interrogative) well enough to ground the model against answering an
    unrelated topic, without another LLM call per turn."""
    return "?" in player_input or bool(_QUESTION_WORDS.search(player_input))


_QUESTION_GROUNDING_LINE = (
    "O jogador fez uma pergunta direta. O interlocutor deve endereçá-la "
    "explicitamente — respondendo, recusando, evitando de forma plausível "
    "e grounded, ou admitindo desconhecimento — mas nunca ignorando-a "
    "para falar de outro assunto que o jogador não trouxe."
)


def _build_current_turn_block(player_input: str) -> str:
    """Phase 24A.1 — makes the player's CURRENT turn visually/semantically
    unmistakable, instead of relying on the model to notice it somewhere
    inside a long prompt. The exact text stays verbatim (never summarized
    or replaced by an intent label) — it remains the one authoritative
    record of what Logan actually said/attempted this turn."""
    lines = [
        "TURNO ATUAL DO JOGADOR",
        "",
        "Entrada exata do jogador (a única fala/ação que realmente aconteceu agora):",
        "",
        f'"{player_input.strip()}"',
        "",
        "Esta é a ação ou fala ATUAL do jogador. Responda a ESTE turno específico.",
        "Não responda a um turno anterior do histórico.",
        "Não gere fala, pensamentos, decisões ou ações voluntárias para o protagonista.",
    ]
    if _looks_like_direct_question(player_input):
        lines.append(_QUESTION_GROUNDING_LINE)
    lines.append("")
    lines.append("FIM DO TURNO ATUAL DO JOGADOR")
    return "\n".join(lines)


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
    current_turn_block = _build_current_turn_block(player_input)
    prompt = (
        f"MODO DA CENA:\n{mode}\n\n"
        f"SCENE CONTEXT:\n{context}\n\n"
        f"{recent_history}\n\n"
        f"{current_turn_block}\n\n"
        "AUTHORITATIVE MECHANICAL FACTS:\n"
        f"{mechanical_summary}\n\n"
        "Escreva somente o próximo momento da cena, em português do Brasil."
    )

    logger.debug("NARRATOR SYSTEM PROMPT\n%s", _SYSTEM_PROMPT)
    logger.debug("SCENE CONTEXT\n%s", context)
    logger.debug("RECENT HISTORY\n%s", recent_history)
    logger.debug("CURRENT TURN BLOCK\n%s", current_turn_block)
    logger.debug("AUTHORITATIVE FACTS\n%s", mechanical_summary)

    raw_response = llm_service.generate(_SYSTEM_PROMPT, prompt)
    logger.debug("RAW NARRATOR RESPONSE\n%s", raw_response)
    response = _strip_prompt_leak(raw_response)
    if response != raw_response.strip():
        logger.warning(
            "Stripped apparent prompt/instruction leakage from raw response.\nRAW:\n%s\nCLEANED:\n%s",
            raw_response, response,
        )

    character_name = _extract_character_name(
        context
    )

    active_interlocutor_name = (
        _extract_active_interlocutor_name(
            context
        )
    )

    simulated_player_names = (
        _extract_simulated_player_names(
            context
        )
    )
    validation_context = (
        f"{context}\n\nAUTHORITATIVE MECHANICAL FACTS\n{mechanical_summary}"
    )

    draft = response

    # Hard violations may request a rewrite. Two attempts are enough: repeated
    # regeneration often degrades a good local-model response and is expensive.
    # Style violations are NEVER included in the rewrite reasons.
    for attempt in range(1, 3):
        empty_violations = _empty_response_violations(draft)
        unfulfilled_speech_promise_violations = (
            [] if empty_violations else _find_unfulfilled_speech_promise_violations(draft)
        )
        canon_violations = [] if empty_violations else _find_canon_violations(
            draft, validation_context, player_input
        )
        meta_violations = [] if empty_violations else _find_meta_awareness_violations(draft, simulated_player_names)
        agency_violations = [] if empty_violations else _protagonist_agency_violations(draft, character_name, mode)
        turn_violations = [] if empty_violations else _fabricated_turn_violations(draft, character_name, active_interlocutor_name)
        unauthorized_combatant_violations = (
            [] if empty_violations else _find_unauthorized_combatant_violations(draft, context)
        )
        unauthorized_speaker_violations = (
            []
            if empty_violations
            else _find_unauthorized_speaker_violations(draft, context, active_interlocutor_name)
        )
        hidden_name_violations = [] if empty_violations else _find_hidden_name_violations(
            draft, context, active_interlocutor_name
        )
        opening_interaction_violations = (
            []
            if empty_violations
            else _find_unsolicited_opening_interaction_violations(
                draft,
                mode,
                active_interlocutor_name,
                simulated_player_names,
            )
        )
        style_violations = [] if empty_violations else _find_style_violations(draft)

        hard_violations = (
            empty_violations
            + unfulfilled_speech_promise_violations
            + canon_violations
            + meta_violations
            + agency_violations
            + turn_violations
            + unauthorized_combatant_violations
            + unauthorized_speaker_violations
            + hidden_name_violations
            + opening_interaction_violations
        )

        logger.debug(
            "REVIEW RESULT (attempt %s)\nEMPTY/LEAK VIOLATIONS: %s\nCANON VIOLATIONS: %s\n"
            "META-AWARENESS VIOLATIONS: %s\nAGENCY VIOLATIONS: %s\nFABRICATED TURN VIOLATIONS: %s\n"
            "UNAUTHORIZED COMBATANT VIOLATIONS: %s\nUNAUTHORIZED SPEAKER VIOLATIONS: %s\n"
            "HIDDEN NAME VIOLATIONS: %s\nOPENING INTERACTION VIOLATIONS: %s\n"
            "STYLE VIOLATIONS: %s",
            attempt,
            empty_violations,
            canon_violations,
            meta_violations,
            agency_violations,
            turn_violations,
            unauthorized_combatant_violations,
            unauthorized_speaker_violations,
            hidden_name_violations,
            opening_interaction_violations,
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
            "preencher a resposta. Se a violação envolve recusar revelar algo, a resposta "
            "corrigida ainda deve reconhecer e responder à pergunta original do jogador (por "
            "exemplo, recusando ou hesitando de forma natural) — nunca mude de assunto para "
            "algo que o jogador não perguntou. Sua resposta deve conter APENAS a narrativa "
            "final, em português — nunca repita este prompt, o rascunho, a lista de violações "
            "ou qualquer instrução."
        )
        logger.debug(
            "NARRATOR REVISION %s HARD REASONS\n%s",
            attempt,
            "\n".join(hard_violations),
        )
        raw_revision = llm_service.generate(_SYSTEM_PROMPT, revision_prompt)
        logger.debug("RAW NARRATOR RESPONSE (REVISION %s)\n%s", attempt, raw_revision)
        draft = _strip_prompt_leak(raw_revision)
        if draft != raw_revision.strip():
            logger.warning(
                "Stripped apparent prompt/instruction leakage from revision %s.\nRAW:\n%s\nCLEANED:\n%s",
                attempt, raw_revision, draft,
            )

    # From this point onward, no unresolved HARD violation is intentionally
    # returned to the player. Style remains non-blocking.
    if not draft.strip():
        safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
        logger.error(
            "FALLBACK REASON: response was empty after stripping leaked prompt/instruction "
            "text on every revision attempt. Returning deterministic safe fallback.\nFALLBACK:\n%s",
            safe,
        )
        return safe

    remaining_unfulfilled_speech_promise = _find_unfulfilled_speech_promise_violations(draft)
    if remaining_unfulfilled_speech_promise:
        # Nothing to trim toward — the whole draft IS the unfulfilled
        # promise, there is no dialogue anywhere in it to keep.
        safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
        logger.error(
            "FALLBACK REASON: draft still promised a reply that never arrived after hard "
            "revisions: %s\nFALLBACK:\n%s",
            remaining_unfulfilled_speech_promise,
            safe,
        )
        return safe

    remaining_style = _find_style_violations(draft)
    remaining_agency = _protagonist_agency_violations(draft, character_name, mode)
    remaining_turn = _fabricated_turn_violations(draft, character_name, active_interlocutor_name)
    remaining_unauthorized_combatant = _find_unauthorized_combatant_violations(draft, context)
    remaining_unauthorized_speaker = _find_unauthorized_speaker_violations(
        draft, context, active_interlocutor_name
    )
    remaining_hidden_names = _find_hidden_name_violations(
        draft, context, active_interlocutor_name
    )
    remaining_opening_interaction = _find_unsolicited_opening_interaction_violations(
        draft,
        mode,
        active_interlocutor_name,
        simulated_player_names,
    )

    logger.debug(
        "REVIEW RESULT (final)\nAGENCY VIOLATIONS: %s\nFABRICATED TURN VIOLATIONS: %s\n"
        "UNAUTHORIZED COMBATANT VIOLATIONS: %s\nUNAUTHORIZED SPEAKER VIOLATIONS: %s\n"
        "HIDDEN NAME VIOLATIONS: %s\nOPENING INTERACTION VIOLATIONS: %s\n"
        "STYLE VIOLATIONS: %s",
        remaining_agency,
        remaining_turn,
        remaining_unauthorized_combatant,
        remaining_unauthorized_speaker,
        remaining_hidden_names,
        remaining_opening_interaction,
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
        trimmed = _drop_agency_violations(draft, character_name, active_interlocutor_name, mode)
        if trimmed:
            logger.warning(
                "FALLBACK REASON: protagonist still had fabricated dialogue/actions after "
                "hard revisions; offending content was dropped: %s\nKEPT:\n%s",
                remaining_agency + remaining_turn,
                trimmed,
            )
            draft = trimmed
        else:
            safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
            logger.error(
                "FALLBACK REASON: protagonist agency violation could not be removed without "
                "emptying the response. Returning deterministic safe fallback instead of the "
                "known-invalid draft: %s\nFALLBACK:\n%s",
                remaining_agency + remaining_turn,
                safe,
            )
            return safe

    # A bystander NPC written as fighting is never acceptable, but the rest of
    # an otherwise-valid combat turn usually is. Drop only the offending
    # paragraph(s) instead of discarding real mechanical narration.
    if remaining_unauthorized_combatant:
        trimmed = _drop_unauthorized_combatant_segments(draft, context)
        if trimmed:
            logger.warning(
                "FALLBACK REASON: draft gave a bystander NPC combat agency after hard "
                "revisions; offending paragraph(s) dropped: %s\nKEPT:\n%s",
                remaining_unauthorized_combatant,
                trimmed,
            )
            draft = trimmed
        else:
            safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
            logger.error(
                "FALLBACK REASON: unauthorized combatant violation could not be removed "
                "without emptying the response. Returning deterministic safe fallback "
                "instead of the known-invalid draft: %s\nFALLBACK:\n%s",
                remaining_unauthorized_combatant,
                safe,
            )
            return safe

    # A bystander NPC given dialogue they were never authorized for (the wrong
    # NPC "answering" instead of the one actually being addressed) — drop only
    # the paragraph(s) that voice them, keeping the rest of the exchange.
    if remaining_unauthorized_speaker:
        trimmed = _drop_unauthorized_speaker_segments(draft, context, active_interlocutor_name)
        if trimmed:
            logger.warning(
                "FALLBACK REASON: draft gave an unauthorized bystander NPC dialogue after "
                "hard revisions; offending paragraph(s) dropped: %s\nKEPT:\n%s",
                remaining_unauthorized_speaker,
                trimmed,
            )
            draft = trimmed
        else:
            safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
            logger.error(
                "FALLBACK REASON: unauthorized speaker violation could not be removed "
                "without emptying the response. Returning deterministic safe fallback "
                "instead of the known-invalid draft: %s\nFALLBACK:\n%s",
                remaining_unauthorized_speaker,
                safe,
            )
            return safe

    # A leaked canonical name taints only the paragraph(s) that mention it —
    # keep the rest of an otherwise-valid turn instead of discarding it whole.
    if remaining_hidden_names:
        trimmed = _drop_hidden_name_segments(draft, context, active_interlocutor_name)
        if trimmed:
            logger.warning(
                "FALLBACK REASON: draft still revealed hidden names after hard revisions; "
                "offending paragraph(s) dropped: %s\nKEPT:\n%s",
                remaining_hidden_names,
                trimmed,
            )
            draft = trimmed
        else:
            safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
            logger.error(
                "FALLBACK REASON: hidden name violation could not be removed without "
                "emptying the response. Returning deterministic safe fallback instead of "
                "the known-invalid draft: %s\nFALLBACK:\n%s",
                remaining_hidden_names,
                safe,
            )
            return safe

    # An opening is only the initial situation. If the model insists on
    # forcing a native NPC encounter after both revisions, do not expose that
    # generated branch to the player.
    if remaining_opening_interaction:
        safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
        logger.error(
            "FALLBACK REASON: opening still initiated an unauthorized interaction after "
            "hard revisions: %s\nFALLBACK:\n%s",
            remaining_opening_interaction,
            safe,
        )
        return safe

    remaining_canon = (
        _find_canon_violations(draft, validation_context, player_input)
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
        validation_context,
        player_input,
        simulated_player_names,
    )

    # The filter removes canon/meta claims but should not be allowed to leak an
    # agency violation that survived due to sentence reshaping. Recheck once.
    if filtered:
        filtered_agency = _protagonist_agency_violations(filtered, character_name, mode)
        filtered_turn = _fabricated_turn_violations(filtered, character_name, active_interlocutor_name)
        if filtered_agency or filtered_turn:
            filtered = _drop_agency_violations(filtered, character_name, active_interlocutor_name, mode)

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
    if mode == "CONTINUATION" and active_interlocutor_name:
        logger.warning(
            "FALLBACK REASON: no supported segment survived canon filtering with an active NPC; "
            "using epistemic refusal"
        )
        logger.debug("FINAL RESPONSE (epistemic fallback)\n— Não sei dizer.")
        return "— Não sei dizer."

    safe = _safe_hard_failure_fallback(mode, active_interlocutor_name)
    logger.error(
        "FALLBACK REASON: no supported segment survived canon filtering and there is no active "
        "NPC for an epistemic refusal. Returning deterministic safe fallback instead of the "
        "known-invalid draft.\nFALLBACK:\n%s",
        safe,
    )
    return safe
