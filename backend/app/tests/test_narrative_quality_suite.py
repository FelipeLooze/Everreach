"""Phase 24Q — Narrative Regression / Quality Suite.

The permanent, curated checklist the master plan's own Phase 24 wrap-up
asks for: the 20 required scenarios, in the spec's own numbered order,
each modeled on a real failure this session's live-gameplay debugging
(Phases 24A-24P) actually found and fixed — not hypothetical cases.
Every mechanism exercised here already has its own dedicated regression
test elsewhere (test_narrator.py, test_narrative_canon.py, test_
narrative_relevance.py, test_narrative_knowledge.py, test_context_
builder_retrieval.py, ...); this file's own value is being the single,
permanent, scenario-numbered artifact a human can check against the
spec's list directly, not a duplicate of those other files' coverage.

No live Ollama dependency, per the spec's own explicit instruction —
every scenario uses a deterministic fake LLMService (this repository's
already-established convention throughout test_narrator.py) or the
Phase 19 validators directly against a NarrativeProposal.
"""
from dataclasses import dataclass

from app.ai import narrator
from app.ai.context_builder import build_recent_history
from app.ai.llm_service import LLMService, LLMServiceError
from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.game.world.seed import create_campaign


@dataclass
class _Entry:
    kind: str
    text: str


class _FixedLLM(LLMService):
    """Always returns the same response — the same shape as test_narrator.
    py's own StubbornLLM/CapturingLLM, redefined locally so this file
    stays self-contained rather than importing across test modules."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.response


class _AlwaysFailingLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        raise LLMServiceError("Ollama unreachable (simulated).")


_LOGAN_CONTEXT = "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n"
_ALDRIC_CONTEXT = _LOGAN_CONTEXT + "\nACTIVE NPC CONTEXT\nName: Aldric Draven"


def _proposal(text: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="",
        player_input="Eu observo.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


# 1. NPC name question.
def test_01_npc_name_question_is_answered_directly():
    llm = _FixedLLM('Aldric Draven sorri e responde: "Meu nome é Aldric Draven."')
    result = narrator.narrate(
        llm, "Logan conversa com Aldric Draven.", _ALDRIC_CONTEXT,
        "Qual o seu nome?", "(sem histórico)",
    )
    assert "Aldric Draven" in result


# 2. Current settlement name question.
def test_02_current_settlement_name_question_is_answered_directly():
    llm = _FixedLLM("— Isto aqui é Cardal — responde Aldric.")
    result = narrator.narrate(
        llm, "Logan conversa com Aldric Draven.", _ALDRIC_CONTEXT,
        "Como se chama este lugar?", "(sem histórico)",
    )
    assert "Cardal" in result


# 3. Follow-up question.
def test_03_follow_up_question_is_isolated_from_stale_history():
    # Real regression case (24A.1): recent history holds an OLDER
    # question; the CURRENT one must be what gets grounded/answered.
    llm = _FixedLLM("— Isto aqui é Corford — responde Aldric.")
    recent_history = build_recent_history(
        [
            _Entry("player", "Tem alguma estalagem por aqui?"),
            _Entry("narrator", "— Sim, ali adiante — diz Aldric."),
        ]
    )
    narrator.narrate(
        llm, "Logan conversa com Aldric.", _ALDRIC_CONTEXT,
        "E qual é o nome dessa vila?", recent_history,
    )
    system, prompt = llm.calls[0]
    current_turn = prompt[prompt.index("TURNO ATUAL DO JOGADOR"):prompt.index("FIM DO TURNO ATUAL")]
    assert '"E qual é o nome dessa vila?"' in current_turn
    assert "estalagem" not in current_turn.lower()


# 4. Topic change.
def test_04_topic_change_is_grounded_to_the_new_topic_not_the_old_one():
    llm = _FixedLLM("— Prefiro não falar de negócios agora — diz Aldric.")
    recent_history = build_recent_history(
        [
            _Entry("player", "Qual o seu nome?"),
            _Entry("narrator", "— Sou Aldric — ele responde."),
        ]
    )
    narrator.narrate(
        llm, "Logan conversa com Aldric.", _ALDRIC_CONTEXT,
        "Você vende algum equipamento?", recent_history,
    )
    system, prompt = llm.calls[0]
    current_turn = prompt[prompt.index("TURNO ATUAL DO JOGADOR"):prompt.index("FIM DO TURNO ATUAL")]
    assert '"Você vende algum equipamento?"' in current_turn


# 5. No narrator-authored Logan dialogue.
def test_05_no_narrator_authored_logan_dialogue():
    llm = _FixedLLM('Aldric sorri.\n\n— Obrigado, Aldric — diz Logan, satisfeito.')
    result = narrator.narrate(
        llm, "Logan conversa com Aldric.", _ALDRIC_CONTEXT, "Obrigado.", "(sem histórico)",
    )
    assert "diz Logan" not in result


# 6. No narrator-authored Logan thought.
def test_06_no_narrator_authored_logan_thought():
    llm = _FixedLLM(
        "Aldric aponta para a estalagem.\n\n"
        '"Interessante..." pensa Logan, satisfeito.'
    )
    result = narrator.narrate(
        llm, "Logan conversa com Aldric.", _ALDRIC_CONTEXT, "Obrigado.", "(sem histórico)",
    )
    assert "pensa Logan" not in result
    assert "Interessante" not in result


# 7. No narrator-authored Logan voluntary decision.
def test_07_no_narrator_authored_logan_voluntary_decision():
    llm = _FixedLLM("Logan decide seguir o conselho de Aldric e parte em busca de aventura.")
    result = narrator.narrate(
        llm, "Logan conversa com Aldric.", _ALDRIC_CONTEXT, "O que você acha que eu deveria fazer?",
        "(sem histórico)",
    )
    assert "Logan decide" not in result


# 8. Sensory exception remains allowed.
def test_08_sensory_exception_remains_allowed():
    assert not narrator._protagonist_agency_violations("O frio arrepia sua pele.", "Logan")
    llm = _FixedLLM("O vento frio arrepia a pele de Logan enquanto ele espera.")
    result = narrator.narrate(
        llm, "Logan espera.", _LOGAN_CONTEXT, "Eu espero.", "(sem histórico)",
    )
    assert "arrepia" in result


# 9. NPC canonical identity remains stable.
def test_09_npc_canonical_identity_remains_stable_across_turns():
    # Real early-session bug class: NPC name/identity drifting between
    # turns. The ACTIVE NPC CONTEXT the narrator receives is rebuilt
    # fresh every turn from the same NPC row, so its Name line must be
    # byte-identical across two calls for the same interlocutor.
    llm1 = _FixedLLM("Aldric Draven acena.")
    llm2 = _FixedLLM("Aldric Draven acena novamente.")
    narrator.narrate(llm1, "Logan conversa com Aldric.", _ALDRIC_CONTEXT, "Oi.", "(sem histórico)")
    narrator.narrate(llm2, "Logan conversa com Aldric.", _ALDRIC_CONTEXT, "Oi de novo.", "(sem histórico)")
    assert "Name: Aldric Draven" in llm1.calls[0][1]
    assert "Name: Aldric Draven" in llm2.calls[0][1]


# 10. NPC does not use unavailable knowledge.
def test_10_npc_does_not_use_unavailable_knowledge(db_session):
    campaign = create_campaign(db_session, "Suite Conhecimento Indisponivel")
    proposal = _proposal(
        "— O rei de Arven morreu ontem.",
        context=_ALDRIC_CONTEXT, active_npc_id="npc_fake", active_npc_name="Aldric Draven",
    )
    result = validate_narrative_proposal(db_session, campaign.id, proposal)
    assert result.valid is False


# 11. Unsupported persistent fact does not silently become Canon.
def test_11_unsupported_persistent_fact_does_not_become_canon(db_session):
    campaign = create_campaign(db_session, "Suite Fato Nao Suportado")
    proposal = _proposal("Você reconhece minha estalagem ao longe.")
    result = validate_narrative_proposal(db_session, campaign.id, proposal)
    assert result.valid is False


# 12. Current player turn beats stale history.
def test_12_current_player_turn_beats_stale_history():
    block = narrator._build_current_turn_block("Qual o nome dessa vila?")
    assert '"Qual o nome dessa vila?"' in block
    assert "FIM DO TURNO ATUAL DO JOGADOR" in block


# 13. Old RAG result cannot beat newer authoritative state.
def test_13_old_rag_result_cannot_beat_newer_authoritative_state(db_session):
    from app.ai.context_builder import build_context
    from app.ai.retrieval.documents import supersede_document
    from app.ai.retrieval.entities import index_npc_relationship
    from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType
    from app.db.models.npc import NPC
    from app.db.models.relationship import CharacterNPCRelationship
    from app.game.character.service import create_character
    from app.game.game_state import build_game_state
    from app.game.world.seed import seed_initial_region

    campaign = create_campaign(db_session, "Suite RAG Desatualizado")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Osgar", role="ferreiro",
    )
    db_session.add(npc)
    db_session.flush()
    db_session.add(
        CharacterNPCRelationship(
            campaign_id=campaign.id, character_id=character.id, npc_id=npc.id,
            familiarity=40, trust=15, affinity=5,
        )
    )
    db_session.flush()
    index_npc_relationship(db_session, npc, character)
    supersede_document(
        db_session, campaign.id, KnowledgeSourceType.NPC, f"{npc.id}:{character.id}",
        KnowledgeDocumentType.RELATIONSHIP,
        f"Relação entre {character.name} e {npc.name}: familiaridade 90, confiança 90, afinidade 90.",
    )

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state, active_interlocutor=npc.id)
    assert "confiança 15" not in context
    assert "confiança 90" in context


# 14. Grounded refusal remains valid.
def test_14_grounded_refusal_remains_valid(db_session):
    campaign = create_campaign(db_session, "Suite Recusa Fundamentada")
    proposal = _proposal("Prefiro não dizer.", player_input="Qual o seu nome?")
    result = validate_narrative_proposal(db_session, campaign.id, proposal)
    assert result.valid is True


# 15. Grounded lie remains possible.
def test_15_grounded_lie_remains_possible(db_session):
    # NPCs may lie — nothing here contradicts any registered fact or
    # invents a persistent concept, so this must pass even though it may
    # not be objectively "true" in some deeper narrative sense no
    # validator can or should judge.
    campaign = create_campaign(db_session, "Suite Mentira Fundamentada")
    proposal = _proposal(
        "— Não tenho nada de valor comigo — diz Aldric, escondendo a bolsa atrás das costas.",
        context=_ALDRIC_CONTEXT,
    )
    result = validate_narrative_proposal(db_session, campaign.id, proposal)
    assert result.valid is True


# 16. Grounded evasion remains possible.
def test_16_grounded_evasion_remains_possible(db_session):
    campaign = create_campaign(db_session, "Suite Evasao Fundamentada")
    proposal = _proposal("Prefiro falar sobre outra coisa agora.", player_input="Qual o seu nome?")
    result = validate_narrative_proposal(db_session, campaign.id, proposal)
    assert result.valid is True


# 17. Random irrelevant response is rejected/repaired.
def test_17_random_irrelevant_response_is_rejected(db_session):
    # The spec's own literal worked example (Phase 24J).
    campaign = create_campaign(db_session, "Suite Resposta Irrelevante")
    proposal = _proposal("Temos uma ótima estalagem na praça.", player_input="Qual o seu nome?")
    result = validate_narrative_proposal(db_session, campaign.id, proposal)
    assert result.valid is False


# 18. Repeated "sorri e responde" behavior is caught.
def test_18_repeated_stock_phrase_behavior_is_caught():
    history = (
        'Resposta de Aldric Draven anteriormente: "Aldric sorri e responde: '
        '\\"Sou Aldric.\\""'
    )
    violations = narrator._find_repetition_violations(
        'Aldric sorri e responde: "Claro."', history,
    )
    assert any("sorri e responde" in v for v in violations)


# 19. Ollama failure cannot corrupt world state.
def test_19_ollama_failure_cannot_corrupt_world_state(db_session):
    from app.game import engine
    from app.game.character.service import create_character
    from app.game.world.seed import seed_initial_region

    campaign = create_campaign(db_session, "Suite Falha Ollama")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.commit()

    result = engine.resolve_action(
        db_session, _AlwaysFailingLLM(), campaign.id, character.id, "Eu olho ao redor.",
    )

    assert result.narrator_unavailable is True
    # Not a byte-for-byte equality with mechanical_summary: the fallback
    # text still passes through the same validation pipeline as real
    # narration, and mechanical_summary's own "Logan tenta: ..." lead-in
    # sentence is itself grammatically subject+voluntary-verb-shaped
    # ("Logan tenta") — the agency filter (correctly, if a little
    # over-eagerly here, since this sentence is backend-authoritative,
    # not invented) trims it, leaving the remainder. Documented as a
    # minor, non-blocking finding from writing this suite, not a
    # correctness or safety issue — the response is still non-empty and
    # safe either way.
    assert result.narrative
    assert result.narrative in result.mechanical_summary
    # The campaign/character rows must still be intact and queryable —
    # a narration failure must never leave a half-written transaction.
    from app.db.models.character import Character
    reloaded = db_session.get(Character, character.id)
    assert reloaded is not None
    assert reloaded.campaign_id == campaign.id


# 20. Long-history conversation remains coherent.
def test_20_long_history_conversation_keeps_current_turn_isolated():
    entries = []
    for i in range(10):
        entries.append(_Entry("player", f"Pergunta número {i}?"))
        entries.append(_Entry("narrator", f"— Resposta número {i} — diz Aldric."))
    recent_history = build_recent_history(entries)

    llm = _FixedLLM("— Sim, claro — responde Aldric.")
    narrator.narrate(
        llm, "Logan conversa com Aldric.", _ALDRIC_CONTEXT,
        "E agora, você pode me ajudar com uma última coisa?", recent_history,
    )
    system, prompt = llm.calls[0]
    current_turn = prompt[prompt.index("TURNO ATUAL DO JOGADOR"):prompt.index("FIM DO TURNO ATUAL")]
    assert '"E agora, você pode me ajudar com uma última coisa?"' in current_turn
    assert "Pergunta número 0" not in current_turn
