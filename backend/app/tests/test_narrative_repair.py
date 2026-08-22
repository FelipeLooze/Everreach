"""Phase 19Q — Narrative Repair."""

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


def test_repair_preserves_valid_claims_and_drops_only_invalid_ones(db_session):
    campaign = create_campaign(db_session, "Reparo Seletivo")
    proposal = _proposal(
        "O vento frio sopra pela praça. Logan decide entrar na taverna.",
        context="CURRENT PLAYER\nName: Logan\n\nCANONICAL LOCATION CONTEXT\nUma taverna aberta.",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False
    assert "O vento frio sopra pela praça." in result.final_text
    assert "Logan decide entrar na taverna." not in result.final_text


def test_repair_falls_back_when_nothing_coherent_survives(db_session):
    """When the entire proposal is a single rejected claim, repair must
    never return a bare empty string — it escalates to Phase 19R's
    immersive safe fallback instead."""
    campaign = create_campaign(db_session, "Reparo Sem Sobra")
    proposal = _proposal("Logan decide fugir imediatamente.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False
    assert result.final_text != ""
    assert "Logan decide fugir imediatamente." not in result.final_text


def test_repair_never_loops_and_returns_in_one_pass(db_session):
    """Bounded repair: a single deterministic pass, never a retry loop —
    this test just confirms validation terminates and returns promptly
    for a proposal with many rejected claims."""
    campaign = create_campaign(db_session, "Reparo Nao Faz Loop")
    text = " ".join(f"Logan decide agir de forma {index}." for index in range(20))
    proposal = _proposal(text)

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False
    assert isinstance(result.final_text, str)
