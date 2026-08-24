"""Phase 19F — Canon Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.game.world.seed import create_campaign


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


def test_persistent_concept_unsupported_by_context_is_rejected(db_session):
    campaign = create_campaign(db_session, "Conceito Sem Suporte")
    proposal = _proposal("Uma ponte antiga cruza o rio logo ali.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False
    assert result.violations


def test_persistent_concept_already_present_in_context_is_allowed(db_session):
    campaign = create_campaign(db_session, "Conceito Ja Suportado")
    proposal = _proposal(
        "A ponte de pedra permanece firme e sólida.",
        context="CURRENT PLAYER\nName: Logan\n\nCANONICAL LOCATION CONTEXT\nUma ponte de pedra liga as duas margens.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_quantified_history_without_canonical_support_is_rejected(db_session):
    campaign = create_campaign(db_session, "Historia Quantificada Sem Apoio")
    proposal = _proposal("Este lugar existe há cinquenta anos.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_ordinary_narration_with_no_canon_claims_passes(db_session):
    campaign = create_campaign(db_session, "Sem Reivindicacao De Canon")
    proposal = _proposal("A luz da manhã se espalha pela praça.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


# --- Phase 24I — Canon & World-Claim Validation Hardening ---
#
# The spec's own required real-failure regression set. "minha estalagem"
# was a real, confirmed bug: _PERSISTENT_CONCEPTS' own regex for
# "estalagem" (r"\bestalagens?\b") could only ever match "estalagen"/
# "estalagens" — never the actual Portuguese word "estalagem" — so this
# exact example silently passed validation before the fix.


def test_regression_minha_estalagem_is_rejected(db_session):
    campaign = create_campaign(db_session, "Estalagem Nao Registrada")
    proposal = _proposal("Você reconhece minha estalagem ao longe.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_regression_predio_do_conselho_is_rejected(db_session):
    campaign = create_campaign(db_session, "Predio Do Conselho Nao Registrado")
    proposal = _proposal("O prédio do conselho fica na praça central.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_regression_ponte_norte_is_rejected(db_session):
    campaign = create_campaign(db_session, "Ponte Norte Nao Registrada")
    proposal = _proposal("A ponte norte conecta as duas margens.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_regression_unsupported_family_relationship_is_rejected(db_session):
    campaign = create_campaign(db_session, "Parentesco Nao Registrado")
    proposal = _proposal("Osgar menciona sua irmã, Elara.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_regression_invented_organization_category_word_is_rejected(db_session):
    campaign = create_campaign(db_session, "Organizacao Inventada")
    proposal = _proposal("Essa organização controla o comércio local.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_regression_invented_persistent_building_is_rejected(db_session):
    campaign = create_campaign(db_session, "Edificio Inventado")
    proposal = _proposal("O edifício da guarda fica perto daqui.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_persistent_concept_survives_when_actually_supported_by_context(db_session):
    # A previously-fixed concept must still be ALLOWED when the context
    # already supports it — the fix must not turn every mention into an
    # unconditional rejection.
    campaign = create_campaign(db_session, "Estalagem Suportada")
    proposal = _proposal(
        "A estalagem continua aberta a esta hora.",
        context="CURRENT PLAYER\nName: Logan\n\nCANONICAL LOCATION CONTEXT\nHá uma estalagem na praça.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_known_remaining_gap_wholly_invented_proper_noun_organization_not_caught(db_session):
    # Documents a deliberate, acknowledged limitation (Phase 24I audit):
    # a fabricated organization name with NO generic category word
    # ("guilda"/"facção"/"organização"/"grupo") anywhere near it cannot
    # be caught by this keyword-based mechanism without risking false
    # positives on ordinary capitalized names (NPCs, places). Left for a
    # future phase rather than attempted here — this test exists so a
    # future fix is a deliberate change to this assertion, not a silent
    # behavior drift.
    campaign = create_campaign(db_session, "Organizacao Sem Palavra Categoria")
    proposal = _proposal("Você percebe o emblema da Guarda de Ferro.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
