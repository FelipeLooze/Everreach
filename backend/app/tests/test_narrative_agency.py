"""Phase 19D — Player Agency Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.game.world.seed import create_campaign


def _proposal(text: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="Logan descansa.",
        player_input="Eu descanso.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def test_invented_protagonist_dialogue_is_rejected(db_session):
    campaign = create_campaign(db_session, "Fala Inventada")
    proposal = _proposal('Logan diz:\n— Onde devo ir agora?')

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False
    assert result.violations


def test_invented_protagonist_decision_is_rejected(db_session):
    campaign = create_campaign(db_session, "Decisao Inventada")
    proposal = _proposal("Logan decide seguir Mira até a floresta.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_invented_protagonist_emotion_is_rejected(db_session):
    campaign = create_campaign(db_session, "Emocao Inventada")
    proposal = _proposal("Logan confia em Osgar e sorri.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_valid_narrative_survives_repair_when_only_one_sentence_is_invalid(db_session):
    """Spec's own repair example, shape-for-shape: one invalid clause
    must not destroy an otherwise valid narration."""
    campaign = create_campaign(db_session, "Reparo Preserva O Valido")
    proposal = _proposal(
        "Osgar entra na taverna carregando seu martelo. Logan sorri e o abraça."
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False
    assert "Osgar entra na taverna carregando seu martelo." in result.final_text
    assert "Logan sorri e o abraça." not in result.final_text


def test_npc_voluntary_behavior_is_never_rejected(db_session):
    """Player agency protects only the PROTAGONIST — an NPC deciding,
    smiling, or feeling something is ordinary, desired narration."""
    campaign = create_campaign(db_session, "Comportamento De NPC Livre")
    proposal = _proposal("Osgar sorri, acena e decide se aproximar.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
    assert result.final_text == proposal.text


def test_involuntary_physical_consequence_is_never_rejected(db_session):
    """An involuntary consequence (backend already resolved the fall) is
    not a voluntary decision — see Phase 19E for the fuller sensory
    policy; this only confirms 19D itself doesn't overreach into it."""
    campaign = create_campaign(db_session, "Consequencia Involuntaria")
    proposal = _proposal(
        "O impacto derruba Logan no chão.",
        mechanical_summary="Logan sofre um golpe e cai.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_mixed_sensory_and_voluntary_sentence_is_still_rejected_as_a_whole(db_session):
    """Sentence-level repair granularity (Phase 19B): the spec's own
    "feels the wind and decides to return" example rejects the whole
    sentence today, since the sensory and voluntary parts share one
    claim — Phase 19Q/19E may later refine this to clause level."""
    campaign = create_campaign(db_session, "Sensorial E Voluntario Juntos")
    proposal = _proposal("Logan sente o vento gelado e decide voltar.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False
    assert "Logan sente o vento gelado e decide voltar." not in result.final_text
