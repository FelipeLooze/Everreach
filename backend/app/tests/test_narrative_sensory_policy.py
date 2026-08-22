"""Phase 19E — Sensory & Physiological Narration Policy.

Mirrors the spec's own VALID/INVALID worked example pairs directly:
SENSATION != EMOTION.
"""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.ai.validation.claims import ClaimCategory, classify_claim, extract_claims
from app.ai.validation.sensory import is_protected_sensory_claim, is_sensory_claim
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


_VALID_SENSORY_EXAMPLES = [
    "O ar frio morde sua pele exposta.",
    "O rugido ecoa pelo vale, forte o bastante para vibrar em seu peito.",
    "Seu coração dispara com o estrondo súbito atrás de você.",
    "Um gosto metálico se espalha pela sua língua depois do impacto.",
    "O cheiro de carne podre paira pesado no ambiente.",
    "A pedra está fria e levemente úmida sob a palma da sua mão.",
]

_INVALID_EMOTION_EXAMPLES = [
    "Logan odeia o frio.",
    "O terror toma conta de Logan.",
    "Logan entra em pânico.",
    "Logan sente alívio.",
    "Logan fica com nojo do cheiro.",
]


def test_every_spec_valid_sensory_example_survives_validation(db_session):
    campaign = create_campaign(db_session, "Exemplos Sensoriais Validos")
    for text in _VALID_SENSORY_EXAMPLES:
        result = validate_narrative_proposal(db_session, campaign.id, _proposal(text))
        assert result.valid is True, f"expected {text!r} to be allowed"
        assert result.final_text == text


def test_every_spec_invalid_emotion_example_is_rejected(db_session):
    campaign = create_campaign(db_session, "Exemplos Emocionais Invalidos")
    for text in _INVALID_EMOTION_EXAMPLES:
        result = validate_narrative_proposal(db_session, campaign.id, _proposal(text))
        assert result.valid is False, f"expected {text!r} to be rejected"


def test_sensation_does_not_imply_emotion_is_added_automatically():
    """The spec's own framing: describing an involuntary physiological
    response must never be automatically continued with an emotional
    interpretation the player didn't provide. This module doesn't
    rewrite narration — it only classifies — so this test only confirms
    the sensory half alone, unaccompanied by an emotion claim, is
    protected and not accidentally paired with one by classification."""
    claim = extract_claims(
        "Um arrepio percorre sua espinha quando o som ecoa mais fundo na caverna.",
        character_name="Logan",
    )[0]

    assert is_sensory_claim(claim)
    assert is_protected_sensory_claim(claim)
    assert not claim.is_(ClaimCategory.PLAYER_VOLUNTARY)


def test_is_protected_sensory_claim_is_false_when_also_player_voluntary():
    categories = classify_claim(
        "Logan sente o vento gelado e decide voltar.", character_name="Logan"
    )
    from app.ai.validation.claims import NarrativeClaim

    claim = NarrativeClaim(index=0, text="Logan sente o vento gelado e decide voltar.", categories=categories)

    assert is_sensory_claim(claim)
    assert not is_protected_sensory_claim(claim)


def test_npc_emotion_is_never_restricted_by_this_policy(db_session):
    """Emotion protection is scoped to the protagonist only — an NPC's
    own emotional state is ordinary, desired narration."""
    campaign = create_campaign(db_session, "Emocao De NPC Livre")
    proposal = _proposal("Osgar sente alívio e sorri ao ver Logan chegar.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
