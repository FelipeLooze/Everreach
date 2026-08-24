from dataclasses import dataclass

from app.ai import context_builder, narrator
from app.ai.llm_service import LLMService


@dataclass
class _Entry:
    kind: str
    text: str


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
        recent_history=(
            "HISTÓRICO DE TROCAS RECENTES\n\n"
            'Turno 1:\nO jogador disse anteriormente: "Bom dia."\n'
            'Resposta narrada anteriormente: "— Bom dia — responde o ancião."'
            "\n\nFIM DO HISTÓRICO DE TROCAS RECENTES"
        ),
    )

    assert result == "Resposta do NPC."
    assert len(llm.calls) == 1
    system, prompt = llm.calls[0]
    assert "NUNCA invente para o protagonista" in system
    assert "próximo momento da cena" in system
    assert "CONFIRMED significa confirmação para aquela entidade específica." in system
    assert "Somente o backend pode alterar o nível de certeza." in system
    assert "MODO DA CENA:\nCONTINUATION" in prompt
    assert "SCENE CONTEXT:" in prompt
    assert "HISTÓRICO DE TROCAS RECENTES" in prompt
    assert "TURNO ATUAL DO JOGADOR" in prompt
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
        "Logan se encontra de pé em uma praça, cercado por outros recém-chegados."
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


def test_opening_does_not_force_a_native_interlocutor_or_reveal_hidden_names():
    llm = StubbornLLM(
        "Um ancião se aproxima de Logan.\n\n"
        "— Bem-vindo a Cardal, no Vale Verdejante. Como posso ajudá-lo?"
    )
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata)\n\n"
        "PLAYER CURRENT LOCATION KNOWLEDGE\n"
        "Current location canonical name known to player: NO\n"
        "Current region canonical name known to player: NO\n\n"
        "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\n"
        "Name: Cardal\nType: VILLAGE\nRegion: Vale Verdejante\n\n"
        "VISIBLE NPCS\n- Osgar Vell (ancião; activity=IDLE)\n\n"
        "ACTIVE NPC CONTEXT\n- none"
    )

    result = narrator.narrate(
        llm,
        "Logan está fisicamente presente no ponto inicial após o transporte.",
        context,
        "(nenhuma ação do jogador; abertura da campanha)",
        "(nenhum histórico)",
        mode="OPENING",
    )

    assert result == "Nada acontece de imediato."
    assert "Cardal" not in result
    assert "Vale Verdejante" not in result
    assert len(llm.calls) == 3


def test_hidden_region_flag_does_not_block_an_already_known_location_name():
    llm = CapturingLLM("A placa no centro da praça traz o nome Cardal.")
    context = (
        "PLAYER CURRENT LOCATION KNOWLEDGE\n"
        "Current location canonical name known to player: YES\n"
        "Known location name: Cardal\n"
        "Current region canonical name known to player: NO\n\n"
        "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\n"
        "Name: Cardal\nType: VILLAGE\nRegion: Vale Verdejante\n\n"
        "ACTIVE NPC CONTEXT\n- none"
    )

    result = narrator.narrate(
        llm,
        "Existe uma placa perceptível no centro da praça.",
        context,
        "Olhar a placa",
        "(nenhum histórico)",
    )

    assert result == llm.response
    assert len(llm.calls) == 1


def test_active_npc_can_reveal_an_unknown_name_only_when_it_is_in_npc_knowledge():
    llm = CapturingLLM("— Você está em Cardal.")
    context = (
        "PLAYER CURRENT LOCATION KNOWLEDGE\n"
        "Current location canonical name known to player: NO\n"
        "Current region canonical name known to player: NO\n\n"
        "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\n"
        "Name: Cardal\nType: VILLAGE\nRegion: Vale Verdejante\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell\n\n"
        "NPC KNOWLEDGE\n- Osgar knows that this settlement is named Cardal."
    )

    result = narrator.narrate(
        llm,
        "Nenhuma mudança mecânica.",
        context,
        "Onde estou?",
        "NARRATOR: Osgar aguarda.",
    )

    assert result == llm.response
    assert len(llm.calls) == 1


def test_look_action_never_grows_into_a_fabricated_player_question():
    llm = StubbornLLM(
        "Osgar observa Logan em silêncio.\n\n"
        "— Agradeço sua ajuda, senhor. O que me aconselha?\n\n"
        "Osgar inclina a cabeça.\n\n"
        "— Conheça os moradores antes de partir."
    )
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata)\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm,
        "Logan observa o espaço ao redor; nenhuma conversa nova foi iniciada.",
        context,
        "Logan olha ao redor",
        "NARRATOR: Osgar está próximo.",
    )

    assert result == "Osgar observa Logan em silêncio."
    assert "Agradeço" not in result
    assert "aconselha" not in result
    assert "Conheça" not in result
    assert len(llm.calls) == 3


def test_npc_cannot_invent_local_economy_resources_or_route_safety():
    llm = StubbornLLM(
        "— Há muitos recursos naturais. Os moradores são fazendeiros, mineiros e "
        "artesãos, e a trilha é segura de dia, mas perigosa à noite por causa dos "
        "animais selvagens."
    )
    context = "ACTIVE NPC CONTEXT\nName: Osgar Vell"

    result = narrator.narrate(
        llm,
        "Nenhuma mudança mecânica.",
        context,
        "Onde estou?",
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


class LeaksTrailingInstructionsLLM(LLMService):
    """Real regression: the model's narrative content is fine, but it appends
    the revision instructions verbatim afterward — text that contains no
    tracked canon/agency keyword, so only leak-stripping (not the canon
    filter) can catch it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return (
            "Osgar observa Logan com um leve sorriso.\n\n"
            "Reescreva somente a narrativa corrigida, em no máximo dois "
            "parágrafos curtos. Corrija apenas as violações listadas. "
            "Preserve todo conteúdo válido do rascunho."
        )


def test_narrator_strips_trailing_instruction_leak_with_no_tracked_keyword():
    llm = LeaksTrailingInstructionsLLM()
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", context, "Olho ao redor.", "(nenhuma troca anterior)"
    )

    assert result == "Osgar observa Logan com um leve sorriso."
    assert "Reescreva somente" not in result
    assert "violações listadas" not in result
    assert len(llm.calls) == 1


class LeaksFullRevisionScaffoldingLLM(LLMService):
    """Real regression, closer to the exact live failure: the first draft has
    a genuine canon violation, and on revision the model echoes the draft,
    the HARD VIOLATIONS TO REMOVE block, AND the trailing instructions,
    instead of writing a corrected narrative."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if len(self.calls) == 1:
            return "Osgar caminha até a floresta e observa o horizonte."
        return (
            "Osgar caminha até a floresta e observa o horizonte.\n\n"
            "HARD VIOLATIONS TO REMOVE:\n- conceito persistente não autorizado "
            "(invenção da resposta): 'floresta'; pode apenas negar ou admitir "
            "desconhecimento, sem validá-lo nem acrescentar detalhes\n\n"
            "Reescreva somente a narrativa corrigida, em no máximo dois "
            "parágrafos curtos. Corrija apenas as violações listadas."
        )


def test_narrator_never_leaks_revision_scaffolding_even_via_safe_fallback():
    llm = LeaksFullRevisionScaffoldingLLM()
    context = "CANONICAL LOCATION CONTEXT\nName: Cardal\nType: VILLAGE"

    result = narrator.narrate(
        llm, "Nenhuma mudança mecânica.", context, "Olho ao redor.", "(nenhuma troca anterior)"
    )

    assert "HARD VIOLATIONS" not in result
    assert "Reescreva somente" not in result
    assert "DRAFT TO REVISE" not in result
    assert "floresta" not in result.lower()

def test_narrator_prompt_contains_exploration_route_guardrails():
    llm = CapturingLLM()

    narrator.narrate(
        llm,
        mechanical_summary="Nenhuma mudança mecânica.",
        context=(
            "PLAYER SPATIAL KNOWLEDGE\n"
            "RUMORED LOCATIONS\n"
            "- Ruínas Distantes [RUMORED]\n\n"
            "CONNECTED LOCATIONS KNOWN TO PLAYER\n"
            "- none"
        ),
        player_input="Por onde posso seguir?",
        recent_history="",
    )

    system, _prompt = llm.calls[0]

    assert (
        "Se uma rota não estiver nessa seção, não ofereça essa rota"
        in system
    )
    assert "não trate rumor como rota navegável" in system
    assert (
        "Um lugar RUMORED não se torna destino navegável"
        in system
    )

def test_narrator_prompt_contains_resolved_travel_guardrails():
    llm = CapturingLLM()

    narrator.narrate(
        llm,
        mechanical_summary=(
            "Hero viajou até o Bosque. "
            "A viagem sofreu DELAY de 5 minutos."
        ),
        context=(
            "CONNECTED LOCATIONS KNOWN TO PLAYER\n"
            "- noroeste -> Bosque (PATH, distância 1)"
        ),
        player_input="Vou até o bosque.",
        recent_history="",
    )

    system, prompt = llm.calls[0]

    assert (
        "O Narrator não resolve a viagem novamente."
        in system
    )
    assert (
        "Um DELAY não autoriza automaticamente:"
        in system
    )
    assert "- combate;" in system
    assert "- emboscada;" in system
    assert "- criatura;" in system

    assert "AUTHORITATIVE MECHANICAL FACTS:" in prompt
    assert "DELAY de 5 minutos" in prompt

def test_narrator_prompt_prevents_fatigue_from_becoming_damage():
    llm = CapturingLLM()

    narrator.narrate(
        llm,
        mechanical_summary=(
            "Hero concluiu a viagem. "
            "FATIGUE causou gasto adicional de 2.0 Stamina."
        ),
        context="CURRENT PLAYER\nName: Hero",
        player_input="Sigo viagem.",
        recent_history="",
    )

    system, prompt = llm.calls[0]

    assert (
        "FATIGUE não significa automaticamente:"
        in system
    )
    assert "- dano;" in system
    assert "- perda de HP;" in system
    assert "- ferimento;" in system
    assert "Não transforme Stamina perdida em HP perdido." in system

    assert "FATIGUE causou gasto adicional de 2.0 Stamina" in prompt

def test_active_transported_person_is_used_as_safe_interlocutor():
    class EmptyLLM(LLMService):
        def __init__(self) -> None:
            self.calls = 0

        def generate(
            self,
            system: str,
            prompt: str,
        ) -> str:
            self.calls += 1
            return ""

    llm = EmptyLLM()

    context = (
        "CURRENT PLAYER\n"
        "Name: Logan "
        "(narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE TRANSPORTED PERSON CONTEXT\n"
        "Name: Kaelen Voss\n\n"
        "VISIBLE TRANSPORTED PEOPLE\n"
        "- Kaelen Voss (Level 0)"
    )

    result = narrator.narrate(
        llm,
        "Nenhuma mudança mecânica.",
        context,
        "Kaelen?",
        "(nenhuma troca anterior)",
    )

    assert (
        result
        == "Kaelen Voss permanece em silêncio."
    )


def test_narrator_drops_unauthorized_combatant_but_keeps_valid_combat_narration():
    llm = StubbornLLM(
        "Um golpe certeiro de Filipe atinge Lobo Selvagem, que recua ferido.\n\n"
        "Talven Brooks corre e ataca Lobo Selvagem para ajudar Filipe."
    )
    context = (
        "CURRENT PLAYER\nName: Filipe (narrator metadata; NPCs do not know it automatically)\n\n"
        "VISIBLE NPCS\n- Talven Brooks (estalajadeiro; activity=WORKING)\n\n"
        "ACTIVE COMBAT PARTICIPANTS\n- Filipe (side=player)\n- Lobo Selvagem (side=hostile)\n\n"
        "ACTIVE NPC CONTEXT\n- none"
    )

    result = narrator.narrate(
        llm,
        "Filipe acerta em Lobo Selvagem, causando 2 de dano (10 → 8 de HP).",
        context,
        "Eu ataco o lobo selvagem!",
        "(sem histórico)",
    )

    assert result == "Um golpe certeiro de Filipe atinge Lobo Selvagem, que recua ferido."
    assert "Talven" not in result
    assert len(llm.calls) == 3


def test_narrator_uses_safe_fallback_when_the_only_content_is_an_unauthorized_combatant():
    llm = StubbornLLM("Talven Brooks salta na frente de Filipe e ataca Lobo Selvagem.")
    context = (
        "CURRENT PLAYER\nName: Filipe (narrator metadata; NPCs do not know it automatically)\n\n"
        "VISIBLE NPCS\n- Talven Brooks (estalajadeiro; activity=WORKING)\n\n"
        "ACTIVE COMBAT PARTICIPANTS\n- Filipe (side=player)\n- Lobo Selvagem (side=hostile)\n\n"
        "ACTIVE NPC CONTEXT\n- none"
    )

    result = narrator.narrate(
        llm,
        "Filipe acerta em Lobo Selvagem, causando 2 de dano (10 → 8 de HP).",
        context,
        "Eu ataco o lobo selvagem!",
        "(sem histórico)",
    )

    assert result == "Nada acontece de imediato."
    assert len(llm.calls) == 3


def test_narrator_drops_only_the_paragraph_that_leaks_a_hidden_name():
    llm = StubbornLLM(
        "Lobo Selvagem uiva e recua, ferido pelo golpe de Filipe.\n\n"
        "Vocês estão em Cardal, e o lobo foge para os becos da vila."
    )
    context = (
        "PLAYER CURRENT LOCATION KNOWLEDGE\n"
        "Current location canonical name known to player: NO\n"
        "Current region canonical name known to player: NO\n\n"
        "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\n"
        "Name: Cardal\nType: VILLAGE\nRegion: Vale Verdejante\n\n"
        "ACTIVE NPC CONTEXT\n- none"
    )

    result = narrator.narrate(
        llm,
        "Filipe acerta em Lobo Selvagem, causando 4 de dano (7 → 3 de HP). "
        "Lobo Selvagem tenta fugir, mas não consegue escapar.",
        context,
        "Eu ataco de novo!",
        "(sem histórico)",
    )

    assert result == "Lobo Selvagem uiva e recua, ferido pelo golpe de Filipe."
    assert "Cardal" not in result
    assert len(llm.calls) == 3


def test_narrator_catches_protagonist_agency_violation_after_a_comma_appositive():
    llm = StubbornLLM(
        "Lobo Selvagem foge, derrotado, pela viela estreita.\n\n"
        "Filipe, ofegante, decide responder com um sorriso cansado."
    )
    context = (
        "CURRENT PLAYER\nName: Filipe (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\n- none"
    )

    result = narrator.narrate(
        llm,
        "Lobo Selvagem tenta fugir e consegue escapar.",
        context,
        "Eu ataco de novo!",
        "(sem histórico)",
    )

    assert result == "Lobo Selvagem foge, derrotado, pela viela estreita."
    assert len(llm.calls) == 3


def test_narrator_drops_unauthorized_npc_speaker_but_keeps_the_active_interlocutors_reply():
    llm = StubbornLLM(
        "Osgar Vell sorri e acena, ouvindo a pergunta com atenção.\n\n"
        'Talven Brooks: "Aqui, jovem, eu cuido bem dos hóspedes da minha estalagem!"'
    )
    context = (
        "CURRENT PLAYER\nName: Filipe (narrator metadata; NPCs do not know it automatically)\n\n"
        "VISIBLE NPCS\n- Talven Brooks (estalajadeiro; activity=WORKING)\n"
        "- Osgar Vell (ancião da vila; activity=IDLE)\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm,
        "Filipe conversa com Osgar Vell (ancião da vila).",
        context,
        "Eu pergunto a Osgar se há uma pousada.",
        "(sem histórico)",
    )

    assert result == "Osgar Vell sorri e acena, ouvindo a pergunta com atenção."
    assert "Talven" not in result
    assert len(llm.calls) == 3


def test_narrator_allows_a_bystander_npc_to_speak_after_being_explicitly_introduced():
    llm = StubbornLLM(
        "Osgar Vell começa a responder, mas para quando Talven Brooks entra correndo na praça.\n\n"
        'Talven Brooks: "Perdão pela interrupção, mas isso é comigo!"'
    )
    context = (
        "CURRENT PLAYER\nName: Filipe (narrator metadata; NPCs do not know it automatically)\n\n"
        "VISIBLE NPCS\n- Talven Brooks (estalajadeiro; activity=WORKING)\n"
        "- Osgar Vell (ancião da vila; activity=IDLE)\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm,
        "Filipe conversa com Osgar Vell (ancião da vila).",
        context,
        "Eu pergunto a Osgar se há uma pousada.",
        "(sem histórico)",
    )

    assert result == llm.response
    assert len(llm.calls) == 1


def test_strip_prompt_leak_cuts_off_a_self_invented_player_narrator_scaffold():
    # Real bug report: instead of echoing the actual prompt/instruction
    # text (what _strip_prompt_leak was built for), the model regressed
    # into simulating a whole future exchange itself, labeling invented
    # turns with its own shorthand for the prompt's "PLAYER INPUT:"
    # convention — "PLAYER:"/"NARRATOR:" — and fabricating several more
    # turns of dialogue/action nobody asked for.
    raw = (
        "O ancião hesita por um momento antes de continuar. "
        "PLAYER: Logan espera ansiosamente pela resposta do ancião\n"
        "NARRATOR: — Poderia me dizer o motivo de sua visita, senhor?"
    )
    stripped = narrator._strip_prompt_leak(raw)
    assert "PLAYER:" not in stripped
    assert "NARRATOR:" not in stripped
    assert stripped == "O ancião hesita por um momento antes de continuar."


def test_narrator_uses_safe_fallback_when_a_promised_reply_never_arrives():
    # Real bug report ("por que quase sempre a mensagem acaba no 'e
    # responde:'"): the model repeatedly narrates right up to the NPC's
    # line — "...e responde:", "Ela se inclina... com um ar
    # confidencial:" — and then never actually delivers the dialogue,
    # especially for questions with no obvious canned answer (the NPC's
    # own name, where to find work). Nothing previously caught "this
    # response promised speech and never gave any" — it wasn't literally
    # an empty string, so _empty_response_violations let it through.
    llm = StubbornLLM(
        "A mulher idosa sorri e responde:\n\n"
        "Ela se inclina levemente para a frente, com um ar confidencial:\n\n"
        "A mulher espera sua resposta, esperançosa de poder estabelecer uma "
        "conexão amigável."
    )
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "VISIBLE NPCS\n- Lena Hallow (estalajadeira; activity=WORKING)\n\n"
        "ACTIVE NPC CONTEXT\nName: Lena Hallow"
    )

    result = narrator.narrate(
        llm,
        "Logan pergunta o nome da estalajadeira.",
        context,
        "Qual o seu nome?",
        "(sem histórico)",
    )

    assert result == "Lena Hallow permanece em silêncio."
    assert len(llm.calls) == 3


def test_narrator_accepts_a_fulfilled_speech_promise():
    llm = StubbornLLM(
        "A mulher sorri e responde:\n\n"
        "— Meu nome é Lena, jovem viajante."
    )
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "VISIBLE NPCS\n- Lena Hallow (estalajadeira; activity=WORKING)\n\n"
        "ACTIVE NPC CONTEXT\nName: Lena Hallow"
    )

    result = narrator.narrate(
        llm,
        "Logan pergunta o nome da estalajadeira.",
        context,
        "Qual o seu nome?",
        "(sem histórico)",
    )

    assert result == llm.response


def test_narrator_accepts_a_fulfilled_speech_promise_in_the_same_paragraph():
    # Regression for a false positive the mid-paragraph promise check
    # introduced: the colon-then-dash reply lives in the SAME paragraph
    # as the promise ("... e responde: — Meu nome é Lena."), not a
    # separate one — _paragraph_has_spoken_dialogue must still recognize
    # it, since _is_dialogue_paragraph alone only recognizes a dash that
    # OPENS a paragraph.
    llm = StubbornLLM("A mulher sorri e responde: — Meu nome é Lena, jovem viajante.")
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "VISIBLE NPCS\n- Lena Hallow (estalajadeira; activity=WORKING)\n\n"
        "ACTIVE NPC CONTEXT\nName: Lena Hallow"
    )

    result = narrator.narrate(
        llm,
        "Logan pergunta o nome da estalajadeira.",
        context,
        "Qual o seu nome?",
        "(sem histórico)",
    )

    assert result == llm.response
    assert len(llm.calls) == 1
    assert len(llm.calls) == 1


def test_narrator_catches_a_whole_fabricated_back_and_forth_with_no_interlocutor():
    # Real bug report: with no interlocutor authorized, the narrator wrote
    # a FULL multi-turn exchange in one response — a fabricated
    # protagonist line attributed only by pronoun ("admitiu ele", no name
    # at all — a shape neither the name-based nor the self-identification
    # check catches), then fabricated NPC dialogue answering questions the
    # player never asked, including inventing the NPC's own name/identity
    # ("Sou Sable Kessler..."). One unattributable quoted line (a scene
    # legitimately opening with an NPC's own greeting) is tolerated by
    # design — this asserts the SECOND one (the fabricated identity
    # reveal, the more damaging half) is caught, not that every trace of
    # the first one is necessarily gone too.
    llm = StubbornLLM(
        "Olhando em torno, Logan percebeu que estava em uma pequena vila.\n\n"
        "— Eu... não tenho certeza sobre onde estou — admitiu ele, sentindo-se "
        "um pouco perdido. — Este é o nome desta aldeia?\n\n"
        "A mulher morena sorriu, aparentando paciência.\n\n"
        "—Sou Sable Kessler, uma ferreira. Minha família vive aqui há gerações."
    )
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "VISIBLE NPCS\n- Sable Kessler (ferreira; activity=WORKING)\n"
    )

    result = narrator.narrate(
        llm,
        "Há mais de uma pessoa aqui. Diga com quem você quer falar.",
        context,
        "Bom dia, senhora. Saberia me dizer onde estou?",
        "(sem histórico)",
    )

    assert "Sable Kessler" not in result


def test_narrator_drops_fabricated_npc_dialogue_when_no_interlocutor_was_authorized():
    # Real bug report: the mechanical layer correctly refused to pick an
    # interlocutor (multiple NPCs nearby, player named no one), so there is
    # no "ACTIVE NPC CONTEXT" at all — yet a small local model wrote a full,
    # specific NPC reply anyway, in the narration-prose-then-inline-quote
    # shape this model actually uses ("Nome verbo, ... 'fala'"), which
    # neither of _paragraph_speaker_among's stricter patterns recognized
    # (no colon-led screenplay line, no speech verb adjacent to the name).
    llm = StubbornLLM(
        "Aldric Draven sorri calorosamente ao ouvir a saudação de Logan.\n\n"
        'Aldric Draven assente, parecendo satisfeito. '
        '"Sim, temos tudo o que você precisa aqui."'
    )
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "VISIBLE NPCS\n- Aldric Draven (ancião da vila; activity=IDLE)\n"
    )

    result = narrator.narrate(
        llm,
        "Há mais de uma pessoa aqui. Diga com quem você quer falar.",
        context,
        "Olá, bom dia senhor. Qual o seu nome?",
        "(sem histórico)",
    )

    assert '"Sim, temos tudo' not in result
    assert "Aldric Draven sorri calorosamente ao ouvir a saudação de Logan." in result


def test_narrator_catches_unattributed_fabricated_reply_that_self_identifies():
    # Real bug report ("ele ignorou o que eu disse e ta conversando
    # sozinho"): a first-contact scene, no active NPC established yet
    # (context has no "ACTIVE NPC CONTEXT" section, matching a real
    # first TALK turn), an NPC's question, then the narrator invented
    # Logan's OWN reply as a plain unattributed dash line with no "diz
    # Logan"/"Logan responde" attribution at all — just first-person
    # self-identification ("Sou Logan"). None of the existing
    # attribution-based checks fire on a line with no name-plus-verb
    # shape; the self-identification itself is the unambiguous tell.
    llm = StubbornLLM(
        "— Bom dia, estranho! — grita alguém. Um homem se aproxima de Logan. "
        "O que te trouxe até aqui?\n\n"
        "— Eu... não sei realmente. Fui transportado para este lugar junto "
        "com muita gente. Sou Logan, se alguém sabe mais do que eu sobre isso."
    )
    context = "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n"

    result = narrator.narrate(
        llm,
        "Há mais de uma pessoa aqui. Diga com quem você quer falar.",
        context,
        "Logan se aproxima de quem falou com ele \"Ola. Quem é voce?\"",
        "(sem histórico)",
    )

    assert "Sou Logan" not in result
    assert len(llm.calls) == 3  # 1 initial + 2 revision attempts, both stubborn


def test_narrator_catches_protagonist_agency_violation_in_screenplay_colon_format():
    llm = StubbornLLM(
        "Osgar Vell aguarda pacientemente.\n\n"
        'Filipe: "Sim, eu adoraria ficar na pousada esta noite."'
    )
    context = (
        "CURRENT PLAYER\nName: Filipe (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Osgar Vell"
    )

    result = narrator.narrate(
        llm,
        "Filipe conversa com Osgar Vell (ancião da vila).",
        context,
        "Eu pergunto a ele se há uma pousada.",
        "(sem histórico)",
    )

    assert result == "Osgar Vell aguarda pacientemente."
    assert len(llm.calls) == 3


# --- Phase 24A.1 — real-failure regression cases (24A.1's own required set) ---
#
# Cases 2/3/6 test the deterministic guarantees this subphase actually
# built (verbatim current-turn isolation, question grounding) — NOT a
# conversational-relevance validator, which 24A.1 explicitly defers to
# later Phase 24 work rather than half-building here.


def test_case1_name_question_current_turn_block_is_grounded_verbatim():
    block = narrator._build_current_turn_block("Olá, bom dia senhor. Qual o seu nome?")
    assert '"Olá, bom dia senhor. Qual o seu nome?"' in block
    assert narrator._QUESTION_GROUNDING_LINE in block
    assert "Não gere fala, pensamentos, decisões ou ações voluntárias para o protagonista." in block


def test_case2_location_question_is_isolated_as_the_current_turn():
    # "O senhor sabe me informar onde estou?" (a real observed failure:
    # the NPC randomly offered an inn instead). 24A.1 guarantees the
    # question is grounded as the CURRENT turn with an explicit
    # must-address instruction; whether the model actually complies is
    # exactly what a future conversational-relevance validator (24J)
    # would enforce, and is out of scope here.
    llm = StubbornLLM("— Não sei dizer ao certo, mas fica perto da praça.")
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Aldric Draven"
    )
    narrator.narrate(
        llm,
        "Logan conversa com Aldric Draven.",
        context,
        "O senhor sabe me informar onde estou?",
        "(sem histórico)",
    )
    system, prompt = llm.calls[0]
    assert '"O senhor sabe me informar onde estou?"' in prompt
    assert narrator._QUESTION_GROUNDING_LINE in prompt


def test_case3_settlement_name_question_is_isolated_as_the_current_turn():
    # "Na verdade eu queria saber qual cidade é essa, senhor. O nome
    # dela." — the real transcript where the response spontaneously
    # switched to discussing "o conselho" instead. Same scope note as
    # case 2 above.
    llm = StubbornLLM("— Isto aqui é Corford.")
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Aldric Draven"
    )
    narrator.narrate(
        llm,
        "Logan conversa com Aldric Draven.",
        context,
        "Na verdade eu queria saber qual cidade é essa, senhor. O nome dela.",
        "(sem histórico)",
    )
    system, prompt = llm.calls[0]
    assert '"Na verdade eu queria saber qual cidade é essa, senhor. O nome dela."' in prompt
    assert narrator._QUESTION_GROUNDING_LINE in prompt


def test_case4_real_fabricated_logan_lines_never_survive():
    # The exact fabricated protagonist lines observed in real gameplay.
    llm = StubbornLLM(
        "Garrick Draven aponta para a estalagem.\n\n"
        "— Obrigado, Garrick. Vou certamente visitar sua casa para descansar — diz Logan.\n\n"
        '"Interessante... Acho que vou dar uma olhada." pensa Logan, satisfeito.'
    )
    context = (
        "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n\n"
        "ACTIVE NPC CONTEXT\nName: Garrick Draven"
    )
    result = narrator.narrate(
        llm,
        "Logan conversa com Garrick Draven.",
        context,
        "Obrigado.",
        "(sem histórico)",
    )
    assert "Agradeço a oferta, senhor Thane" not in result
    assert "Acho que vou dar uma olhada" not in result
    assert "diz Logan" not in result


def test_case5_history_leak_labels_never_reach_final_output():
    llm = StubbornLLM(
        "Aldric hesita por um momento.\n\n"
        "PLAYER: Logan espera ansiosamente pela resposta\n"
        "NARRATOR: — Poderia me dizer o motivo de sua visita?"
    )
    context = "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n"
    result = narrator.narrate(
        llm,
        "Logan conversa com Aldric.",
        context,
        "Qual o seu nome?",
        "(sem histórico)",
    )
    assert "PLAYER:" not in result
    assert "NARRATOR:" not in result


def test_case6_current_question_is_structurally_separated_from_stale_history():
    # Recent history contains an OLDER lodging question; current input
    # asks the village name. 24A.1's guarantee is structural: the two
    # never blur into the same block, and the current one is the only
    # text inside TURNO ATUAL DO JOGADOR.
    llm = StubbornLLM("— Isto aqui é Corford.")
    context = "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n"
    recent_history = context_builder.build_recent_history(
        [
            _Entry("player", "Tem alguma estalagem por aqui?"),
            _Entry("narrator", "— Sim, ali adiante — diz o ancião."),
        ]
    )
    narrator.narrate(
        llm,
        "Logan conversa com o ancião.",
        context,
        "Qual o nome dessa vila?",
        recent_history,
    )
    system, prompt = llm.calls[0]
    current_turn_start = prompt.index("TURNO ATUAL DO JOGADOR")
    current_turn_end = prompt.index("FIM DO TURNO ATUAL DO JOGADOR")
    current_turn_text = prompt[current_turn_start:current_turn_end]
    assert '"Qual o nome dessa vila?"' in current_turn_text
    assert "estalagem" not in current_turn_text.lower()
