"""Phase 24J — Conversational Relevance Validation.

The spec's own worked example set, plus the real regression this
subphase caught and fixed: a first, broader-enforcement version of this
validator rejected a legitimate, paraphrased answer to "como se chama
este lugar?" (a place-name question, not a question about the NPC's own
identity) because the response shared no literal words with the
question and didn't mention the NPC's own name either — see
app.ai.validation.relevance's module docstring for the full story.
Enforcement is deliberately narrow because of that: only a genuine
self-identity question ("qual o SEU nome") is ever rejected.
"""
from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.ai.validation.relevance import RelevanceOutcome, classify_relevance
from app.game.world.seed import create_campaign


def _proposal(text: str, player_input: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan\n\nACTIVE NPC CONTEXT\nName: Aldric Draven",
        mechanical_summary="",
        player_input=player_input,
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
        active_npc_id="npc_fake",
        active_npc_name="Aldric Draven",
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


# --- classify_relevance() — the spec's own worked example set ---


def test_classify_direct_answer_is_addressed():
    outcome = classify_relevance("Qual o seu nome?", "Meu nome é Aldric.", "Aldric Draven")
    assert outcome == RelevanceOutcome.ADDRESSED


def test_classify_explicit_refusal_is_deliberately_refused():
    outcome = classify_relevance("Qual o seu nome?", "Prefiro não dizer.", "Aldric Draven")
    assert outcome == RelevanceOutcome.DELIBERATELY_REFUSED


def test_classify_dismissal_is_deliberately_refused():
    outcome = classify_relevance("Qual o seu nome?", "Você não precisa saber.", "Aldric Draven")
    assert outcome == RelevanceOutcome.DELIBERATELY_REFUSED


def test_classify_random_topic_drift_is_not_addressed():
    # The spec's own literal invalid example.
    outcome = classify_relevance(
        "Qual o seu nome?", "Temos uma ótima estalagem na praça.", "Aldric Draven"
    )
    assert outcome == RelevanceOutcome.NOT_ADDRESSED


def test_classify_plausible_ignorance_is_recognized():
    outcome = classify_relevance("Qual o seu nome?", "Não sei dizer ao certo.", "Aldric Draven")
    assert outcome == RelevanceOutcome.PLAUSIBLE_IGNORANCE


def test_classify_greeting_has_nothing_mandatory_to_address():
    outcome = classify_relevance("Olá, bom dia.", "Bom dia! Como posso ajudar?", "Aldric Draven")
    assert outcome == RelevanceOutcome.ADDRESSED


# --- The real regression this subphase found and fixed ---


def test_classify_place_name_question_is_not_misjudged_as_npc_identity():
    outcome = classify_relevance(
        "— Com licença, Aldric, como se chama este lugar?",
        "— Isto aqui é Cardal, uma vila tranquila do Vale Verdejante.",
        "Aldric Draven",
    )
    assert outcome == RelevanceOutcome.ADDRESSED


# --- validate_conversational_relevance() — the registered Phase 19 validator ---


def test_validator_rejects_the_spec_worked_example(db_session):
    campaign = create_campaign(db_session, "Deriva De Topico")
    proposal = _proposal("Temos uma ótima estalagem na praça.", "Qual o seu nome?")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_validator_allows_a_direct_answer(db_session):
    campaign = create_campaign(db_session, "Resposta Direta")
    proposal = _proposal("Meu nome é Aldric.", "Qual o seu nome?")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_validator_allows_an_explicit_refusal(db_session):
    campaign = create_campaign(db_session, "Recusa Explicita")
    proposal = _proposal("Prefiro não dizer.", "Qual o seu nome?")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_validator_allows_plausible_ignorance(db_session):
    campaign = create_campaign(db_session, "Desconhecimento Plausivel")
    proposal = _proposal("Não sei dizer ao certo.", "Qual o seu nome?")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_validator_does_not_enforce_non_identity_acts(db_session):
    # Deliberately unenforced (see module docstring) — a location
    # question answered with a paraphrased, non-overlapping response
    # must never be rejected by this validator. (Response text avoids
    # any _PERSISTENT_CONCEPTS keyword so only the relevance validator
    # under test is exercised here, not Phase 24I's canon validator.)
    campaign = create_campaign(db_session, "Pergunta De Local Nao Reforcada")
    proposal = _proposal("Isto aqui é Cardal.", "Como se chama este lugar?")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_validator_ignores_a_third_party_name_question(db_session):
    # "Quem é aquele homem?" has no second-person self-reference — it's
    # not asking about the active NPC's own identity, so this validator
    # must not apply the strict active-NPC-name check to it.
    campaign = create_campaign(db_session, "Pergunta Sobre Terceiro")
    proposal = _proposal(
        "Ah, aquele é só um viajante de passagem, não sei o nome dele.",
        "Quem é aquele homem ali?",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_validator_leaves_ordinary_statements_alone(db_session):
    campaign = create_campaign(db_session, "Declaracao Comum")
    proposal = _proposal("O homem observa Logan em silêncio.", "Eu sento perto da fogueira.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
