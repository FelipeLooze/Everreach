from dataclasses import dataclass

from app.ai import context_builder, narrator
from app.ai.llm_service import LLMService


class CapturingLLM(LLMService):
    def __init__(self, response: str = "Resposta do NPC.") -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.response


class RevisingLLM(LLMService):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.responses = [
            'Osgar olha para o lado como se pesasse a pergunta. "Sou daqui."',
            "Osgar faz uma breve pausa.\n\n— Sou daqui.",
        ]

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.responses[len(self.calls) - 1]


class WorldbuildingRevisingLLM(LLMService):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.responses = [
            "— Não há templo, mas existe uma capela ao sul.",
            "— Não há templo em Cardal.",
        ]

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.responses[len(self.calls) - 1]


class StubbornLLM(LLMService):
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.response


class AgencyRevisingLLM(LLMService):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.responses = [
            "— Bom dia — diz Osgar.\n\n— Ele apenas brilha — responde Logan, sorrindo.",
            "— Bom dia — diz Osgar. — O sol já nasceu.",
        ]

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.responses[len(self.calls) - 1]


@dataclass
class HistoryItem:
    kind: str
    text: str


def test_narrator_applies_system_prompt_and_all_dynamic_sections():
    llm = CapturingLLM()

    result = narrator.narrate(
        llm,
        mechanical_summary="Nenhuma mudança mecânica.",
        context="Local: praça; NPC presente: um ancião.",
        player_input='"O senhor é desta cidade?"',
        recent_history="PLAYER: Bom dia.\nNARRATOR: — Bom dia — responde o ancião.",
    )

    assert result == "Resposta do NPC."
    assert len(llm.calls) == 1
    system, prompt = llm.calls[0]
    assert "NUNCA invente para o protagonista" in system
    assert "próximo momento da cena" in system
    assert "MODO DA CENA:\nCONTINUATION" in prompt
    assert "SCENE CONTEXT:" in prompt
    assert "RECENT HISTORY:" in prompt
    assert "PLAYER INPUT:" in prompt
    assert '"O senhor é desta cidade?"' in prompt
    assert "AUTHORITATIVE MECHANICAL FACTS:" in prompt


def test_opening_mode_forbids_an_initial_player_action():
    llm = CapturingLLM()

    narrator.narrate(
        llm,
        mechanical_summary="Estado inicial do mundo.",
        context="Local: uma vila.",
        player_input="(nenhuma ação do jogador)",
        recent_history="(nenhum histórico)",
        mode="OPENING",
    )

    system, prompt = llm.calls[0]
    assert "Somente durante OPENING é permitido narrar o estado físico resultante desse transporte" in system
    assert "MODO DA CENA:\nOPENING" in prompt
    assert "(nenhuma ação do jogador)" in prompt


def test_opening_mode_permits_the_protagonist_as_subject_of_the_sync_event():
    """Regression: the code-level agency check must know about the ABERTURA
    exception it's supposed to enforce, or it silently strips out the very
    synchronization scene the prompt was told to write."""
    llm = CapturingLLM(
        "Logan se encontra de pé na praça de Cardal, cercado por outros recém-chegados.\n\n"
        "— Bem-vindo, jovem — diz Osgar Vell, erguendo-se de sua cadeira."
    )
    context = "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)"

    result = narrator.narrate(
        llm, "Primeira Chegada.", context,
        "(nenhuma ação do jogador; abertura da campanha)", "(nenhum histórico)",
        mode="OPENING",
    )

    assert result == llm.response
    assert len(llm.calls) == 1


def test_continuation_mode_still_forbids_the_protagonist_as_subject():
    """The OPENING exception must not leak into ordinary turns."""
    llm = AgencyRevisingLLM()
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm, "Logan falou somente: Bom dia.", context, "— Bom dia.", "(nenhuma troca anterior)",
    )

    assert result == "— Bom dia — diz Osgar. — O sol já nasceu."
    assert len(llm.calls) == 2


def test_recent_history_keeps_only_the_small_latest_window():
    entries = [HistoryItem(kind="player", text=f"mensagem {index}") for index in range(8)]

    history = context_builder.build_recent_history(entries, max_entries=3)

    assert "mensagem 4" not in history
    assert "mensagem 5" in history
    assert "mensagem 6" in history
    assert "mensagem 7" in history

def test_narrator_does_not_regenerate_for_long_response_style_only():
    class ProportionalLLM(LLMService):
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, system: str, prompt: str) -> str:
            self.calls += 1
            return "Um.\n\nDois.\n\nTrês.\n\nQuatro."

    llm = ProportionalLLM()

    result = narrator.narrate(
        llm,
        "Nenhuma mudança.",
        "Contexto.",
        "Olho ao redor.",
        "",
    )

    assert result == "Um.\n\nDois.\n\nTrês.\n\nQuatro."
    assert llm.calls == 1


def test_narrator_returns_plain_text_without_mutating_mechanical_data():
    llm = CapturingLLM("Osgar faz uma pausa.\n\n— Sou de Cardal, sim.")
    game_state = {"hp": 20, "mana": 10, "level": 0, "location": "Cardal"}
    before = game_state.copy()

    result = narrator.narrate(
        llm,
        mechanical_summary="Nenhuma mudança mecânica.",
        context="Osgar está presente.",
        player_input='"O senhor é desta cidade?"',
        recent_history="NARRATOR: Osgar aguarda.",
    )

    assert isinstance(result, str)
    assert result == "Osgar faz uma pausa.\n\n— Sou de Cardal, sim."
    assert game_state == before


def test_narrator_revises_new_protagonist_dialogue_or_actions():
    llm = AgencyRevisingLLM()
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm,
        "Logan falou somente: Bom dia.",
        context,
        "— Bom dia.",
        "(nenhuma troca anterior)",
    )

    assert result == "— Bom dia — diz Osgar. — O sol já nasceu."
    assert len(llm.calls) == 2
    assert "não escreva novas falas" in llm.calls[1][1]


class StubbornAgencyLLM(LLMService):
    """Keeps fabricating a new line of protagonist dialogue no matter how many
    times the narrator is asked to revise — simulates a weak local model that
    doesn't reliably follow the agency rule."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return (
            "— Osgar sorri e acena com a cabeça.\n\n"
            "— Entendo — diz Logan, inclinando-se para frente. — O que posso fazer por aqui?"
        )


def test_narrator_drops_stubborn_fabricated_protagonist_dialogue_instead_of_accepting_it():
    llm = StubbornAgencyLLM()
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", context, "Cidade grande, né?", "(nenhuma troca anterior)"
    )

    assert "diz Logan" not in result
    assert "O que posso fazer por aqui" not in result
    assert result == "— Osgar sorri e acena com a cabeça."
    assert len(llm.calls) == 3


class StubbornUnnamedFabricatedTurnLLM(LLMService):
    """Fabricates a whole extra conversational turn — the player's reply AND the
    NPC's reaction to it — without ever naming the protagonist in the fabricated
    reply itself. Simulates the real regression: an unattributed dash-led line
    followed by an NPC 'reacting to the player's decision'."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return (
            "— Venha conferir nossa cozinha! O que me diz? — pergunta Talven, sorridente.\n\n"
            "— Agradeço a gentileza, mas ainda estou ponderando onde ficar esta noite.\n\n"
            "Talven Brooks assente com entendimento e respeita o desejo de Logan de tomar "
            "uma decisão."
        )


def test_narrator_drops_unnamed_fabricated_player_turn_and_the_npcs_reaction_to_it():
    llm = StubbornUnnamedFabricatedTurnLLM()
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Talven Brooks"
    )

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", context, "E o que seria?", "(nenhuma troca anterior)"
    )

    assert "Agradeço a gentileza" not in result
    assert "Logan" not in result
    assert "respeita o desejo" not in result
    assert result == "— Venha conferir nossa cozinha! O que me diz? — pergunta Talven, sorridente."
    assert len(llm.calls) == 3


class StubbornUnnamedTurnNoReactionPhraseLLM(LLMService):
    """Same bug shape as StubbornUnnamedFabricatedTurnLLM, but the NPC just
    keeps talking after the fabricated line instead of using any explicit
    'reacts to a decision' phrasing — the general structural check must catch
    this even without that specific wording."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return (
            "Osgar sorri, compreendendo a curiosidade do rapaz.\n\n"
            "— Claro que é grande! Cardal é apenas uma pequena pérola no vasto reino.\n\n"
            "— Apenas viajando, explorando. E você, senhor Osgar, há quanto tempo mora aqui?\n\n"
            "Osgar ri baixinho.\n\n"
            "— Ah, há mais tempo do que gostaria de admitir, jovem."
        )


def test_narrator_drops_fabricated_turn_even_without_an_explicit_reaction_phrase():
    llm = StubbornUnnamedTurnNoReactionPhraseLLM()
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", context, "Cidade grande, né?", "(nenhuma troca anterior)"
    )

    assert "Apenas viajando" not in result
    assert "há quanto tempo mora aqui" not in result
    assert "Ah, há mais tempo" not in result
    assert result == (
        "Osgar sorri, compreendendo a curiosidade do rapaz.\n\n"
        "— Claro que é grande! Cardal é apenas uma pequena pérola no vasto reino."
    )
    assert len(llm.calls) == 3


def test_narrator_does_not_truncate_a_legitimate_same_speaker_monologue():
    """A monologue split across paragraphs, where a middle paragraph doesn't
    re-state the NPC's name, must NOT be mistaken for a fabricated player turn —
    only an unattributed line immediately followed by the NPC's name again
    should trigger the structural drop."""
    llm = CapturingLLM(
        "Osgar sorri, olhando para o horizonte.\n\n"
        "— Cardal é pequena, mas cada pedra daqui tem uma história.\n\n"
        "— As pessoas cuidam umas das outras, geração após geração."
    )
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", context, "Me conte sobre a vila.", "(nenhuma troca anterior)"
    )

    assert result == llm.response
    assert len(llm.calls) == 1


class StubbornPlayerFramedTurnLLM(LLMService):
    """Real regression shape: a narration beat frames the PLAYER as about to
    respond ("Logan sente-se... e responde"), immediately followed by an
    unattributed dialogue line that is that fabricated response — with no
    further NPC paragraph afterward to confirm it via the 'next paragraph'
    heuristic. The narration beat itself must be enough to catch this."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return (
            "Osgar olha para Logan com um sorriso amigável e atento.\n\n"
            "— Bem-vindo a Cardal, jovem. O que posso fazer por você?\n\n"
            "Logan sente-se mais à vontade e responde com um sorriso.\n\n"
            "— Obrigado, senhor Osgar. Estou apenas explorando a região."
        )


def test_narrator_drops_fabricated_turn_framed_by_a_player_narration_beat():
    llm = StubbornPlayerFramedTurnLLM()
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm, "Logan conversa com Osgar Vell.", context,
        '"Olá, boa tarde, senhor. Como está?" diz Logan se aproximando de Osgar',
        "(nenhuma troca anterior)",
    )

    assert "Logan sente-se" not in result
    assert "Obrigado, senhor Osgar" not in result
    assert result == (
        "Osgar olha para Logan com um sorriso amigável e atento.\n\n"
        "— Bem-vindo a Cardal, jovem. O que posso fazer por você?"
    )
    assert len(llm.calls) == 3


def test_system_prompt_contains_no_campaign_specific_names():
    llm = CapturingLLM()
    narrator.narrate(llm, "fato", "contexto", "entrada", "histórico")
    system, _prompt = llm.calls[0]

    assert "Cardal" not in system
    assert "Osgar" not in system
    assert "Logan" not in system


def test_narrator_does_not_regenerate_for_detectable_style_violations():
    llm = RevisingLLM()

    result = narrator.narrate(
        llm,
        "Nenhuma mudança mecânica.",
        "Personagem: Hero, Nível 0\nNPCs presentes: Osgar",
        '"O senhor é daqui?"',
        "NARRATOR: Osgar aguarda.",
    )

    assert result == 'Osgar olha para o lado como se pesasse a pergunta. "Sou daqui."'
    assert len(llm.calls) == 1


def test_narrator_revises_unregistered_persistent_worldbuilding():
    llm = WorldbuildingRevisingLLM()

    result = narrator.narrate(
        llm,
        "Nenhuma mudança mecânica.",
        "CANONICAL LOCATION CONTEXT\nName: Cardal\nType: VILLAGE\nNPC KNOWLEDGE\n- Cardal é uma vila.",
        "Tem algum templo aqui?",
        "NARRATOR: Osgar aguarda.",
    )

    assert result == "— Não há templo em Cardal."
    assert len(llm.calls) == 2
    revision_prompt = llm.calls[1][1]
    assert "conceito persistente não autorizado" in revision_prompt
    assert "capela" in revision_prompt
    assert "templo" in revision_prompt


class StubbornNpcNamesTheGameLLM(LLMService):
    """An NPC says the game's name out loud in direct dialogue — NPCs must
    never reveal awareness that they live inside a game."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return (
            "Osgar observa as luzes com espanto.\n\n"
            "— Este servidor é perigoso. Vocês deveriam fazer logout. — diz Osgar Vell."
        )


def test_narrator_drops_npc_line_that_names_the_game():
    llm = StubbornNpcNamesTheGameLLM()
    context = (
        "CANONICAL LOCATION CONTEXT\nName: Cardal\nType: VILLAGE\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm, "Primeira Chegada.", context,
        "(nenhuma ação do jogador; abertura da campanha)", "(nenhum histórico)",
        mode="OPENING",
    )

    assert "Everreach" not in result
    assert len(llm.calls) == 3


class StubbornNpcClaimsToBePlayerLLM(LLMService):
    """An NPC claims to be a player itself, without ever saying 'Everreach' —
    the check must catch meta-game vocabulary generally, not just the game's
    literal name."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return (
            "Osgar Vell sorri ao ver a multidão surgir na praça.\n\n"
            "— Bem-vindo ao Vale Verdejante! Como pode ver, todos nós somos jogadores "
            "como você, vindos de diferentes mundos."
        )


def test_narrator_drops_npc_line_that_claims_to_be_a_player():
    llm = StubbornNpcClaimsToBePlayerLLM()
    context = (
        "CANONICAL LOCATION CONTEXT\nName: Cardal\nType: VILLAGE\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm, "Primeira Chegada.", context,
        "(nenhuma ação do jogador; abertura da campanha)", "(nenhum histórico)",
        mode="OPENING",
    )

    assert "jogadores" not in result.lower()
    assert len(llm.calls) == 3


def test_narrator_allows_a_simulated_player_to_use_game_vocabulary():
    """Unlike NPCs, simulated players are allowed to know they're in a game —
    a line naming one of them must survive even if it uses meta-game terms."""
    llm = CapturingLLM(
        "Corren Ashvale se aproxima, ainda desorientado.\n\n"
        "— Um momento eu estava no menu de login, e agora... isso. Você também é "
        "jogador?"
    )
    context = (
        "CANONICAL LOCATION CONTEXT\nName: Cardal\nType: VILLAGE\n\n"
        "ACTIVE NPC CONTEXT\n- none\n\n"
        "VISIBLE PLAYERS\n- Corren Ashvale (Level 0)"
    )

    result = narrator.narrate(
        llm, "Primeira Chegada.", context,
        "(nenhuma ação do jogador; abertura da campanha)", "(nenhum histórico)",
        mode="OPENING",
    )

    assert result == llm.response
    assert len(llm.calls) == 1


def test_narrator_uses_safe_npc_fallback_when_revisions_keep_inventing():
    llm = StubbornLLM(
        "— Depois do rio há um vale fértil, pescadores e uma trilha que segue para longe."
    )
    context = (
        "ACTIVE NPC CONTEXT\nName: Osgar\n\n"
        "PLAYER INPUT CANON CHECK\n"
        "- NPC KNOWLEDGE says where the known creek is, but nothing about what exists beyond it; "
        "admit that gap."
    )

    result = narrator.narrate(
        llm,
        "Nenhuma mudança mecânica.",
        context,
        "O que existe depois do rio?",
        "NARRATOR: Osgar aguarda.",
    )

    assert result == "— Não sei dizer."
    assert len(llm.calls) == 3


def test_narrator_rejects_an_invented_history_for_a_canonical_place():
    llm = StubbornLLM(
        "— Antes, a praça era um campo aberto, e os moradores jogavam ali aos domingos."
    )
    context = (
        "CANONICAL LOCATION CONTEXT\nName: Cardal\nType: VILLAGE\n"
        "Description: Uma vila ao redor de uma praça.\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm,
        "Nenhuma mudança mecânica.",
        context,
        "O senhor nasceu aqui?",
        "NARRATOR: Osgar aguarda.",
    )

    assert result == "— Não sei dizer."
    assert len(llm.calls) == 3


# --- Regression tests: "— Não sei dizer." must not be a universal fallback ---
# (see section 9 of the bugfix request — Teste A through Teste G)

_ACTIVE_NPC_CONTEXT = "ACTIVE NPC CONTEXT\nName: Osgar Vell\n\nPLAYER INPUT CANON CHECK\n- no conflict"


def test_teste_a_greeting_is_not_forced_into_epistemic_refusal():
    llm = CapturingLLM("— Bom dia — responde Osgar.")

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", _ACTIVE_NPC_CONTEXT, "Bom dia.", "(nenhuma troca anterior)"
    )

    assert result == "— Bom dia — responde Osgar."
    assert result != "— Não sei dizer."
    assert len(llm.calls) == 1


def test_teste_b_npc_can_answer_a_wellbeing_question_without_a_knowledge_fact():
    llm = CapturingLLM("— Estou bem, obrigado por perguntar.")

    result = narrator.narrate(
        llm,
        "Nenhuma mudança mecânica.",
        _ACTIVE_NPC_CONTEXT,
        "Como o senhor está?",
        "(nenhuma troca anterior)",
    )

    assert result == "— Estou bem, obrigado por perguntar."
    assert len(llm.calls) == 1


def test_teste_c_question_about_the_day_uses_observable_state_not_canon():
    llm = CapturingLLM("— Até agora, tranquilo.")

    result = narrator.narrate(
        llm,
        "Nenhuma mudança mecânica.",
        _ACTIVE_NPC_CONTEXT,
        "Como está o dia?",
        "(nenhuma troca anterior)",
    )

    assert result == "— Até agora, tranquilo."
    assert len(llm.calls) == 1


def test_teste_d_unsupported_road_claim_is_not_invented():
    llm = StubbornLLM(
        "— Sim, há uma estrada segura que leva direto até o topo da montanha ao norte."
    )
    context = (
        "CANONICAL LOCATION CONTEXT\nName: Cardal\nType: VILLAGE\n\n" + _ACTIVE_NPC_CONTEXT
    )

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", context, "Existe uma estrada para o norte?", "(nenhuma troca anterior)"
    )

    assert "estrada" not in result.lower() or result == "— Não sei dizer."
    assert result == "— Não sei dizer."
    assert len(llm.calls) == 3


def test_teste_e_does_not_accept_an_unsupported_premise_about_a_castle():
    llm = StubbornLLM("— Sim, há um castelo antigo no topo da colina ao norte.")
    context = (
        "CANONICAL LOCATION CONTEXT\nName: Cardal\nType: VILLAGE\n\n" + _ACTIVE_NPC_CONTEXT
    )

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", context, "Tem um castelo ao norte, certo?", "(nenhuma troca anterior)"
    )

    assert "castelo" not in result.lower()
    assert result == "— Não sei dizer."
    assert len(llm.calls) == 3


def test_teste_f_gibberish_input_gets_a_reaction_not_a_forced_refusal():
    llm = CapturingLLM("— Como? — pergunta Osgar, confuso.")

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", _ACTIVE_NPC_CONTEXT, "teste", "(nenhuma troca anterior)"
    )

    assert result != "— Não sei dizer."
    assert result == "— Como? — pergunta Osgar, confuso."


def test_teste_g_valid_social_reply_survives_when_only_part_is_unsupported():
    llm = StubbornLLM("— Bom dia. Há uma estrada secreta ao norte que leva a um castelo.")
    context = (
        "CANONICAL LOCATION CONTEXT\nName: Cardal\nType: VILLAGE\n\n" + _ACTIVE_NPC_CONTEXT
    )

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", context, "Bom dia! Existe um caminho secreto por aqui?", "(nenhuma troca anterior)"
    )

    assert result == "— Bom dia."
    assert "estrada" not in result.lower()
    assert "castelo" not in result.lower()
    assert len(llm.calls) == 3
