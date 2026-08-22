"""Phase 19J — Item / Equipment / Currency Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.core.enums import CombatActorType
from app.game.character.service import create_character
from app.game.economy.wallet import deposit, get_or_create_holding
from app.game.world.seed import create_campaign


def _proposal(text: str, *, character_id, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="",
        player_input="Eu pago.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
        character_id=character_id,
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def test_claimed_payment_exceeding_actual_funds_is_rejected(db_session):
    campaign = create_campaign(db_session, "Pagamento Sem Fundos")
    character = create_character(db_session, campaign.id, "Logan")
    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    deposit(db_session, holding, 500, reason="saldo inicial de teste")

    proposal = _proposal(
        "Vinte moedas de Ouro são colocadas sobre o balcão por você.", character_id=character.id,
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_claimed_payment_within_actual_funds_is_allowed(db_session):
    campaign = create_campaign(db_session, "Pagamento Com Fundos")
    character = create_character(db_session, campaign.id, "Logan")
    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    deposit(db_session, holding, 3_000_000, reason="saldo inicial de teste")

    proposal = _proposal(
        "Vinte moedas de Ouro são colocadas sobre o balcão por você.", character_id=character.id,
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_narration_with_no_currency_claim_is_never_checked(db_session):
    campaign = create_campaign(db_session, "Sem Reivindicacao De Moeda")
    character = create_character(db_session, campaign.id, "Logan")

    proposal = _proposal("O balcão permanece vazio.", character_id=character.id)

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_small_silver_payment_within_funds_is_allowed(db_session):
    campaign = create_campaign(db_session, "Pagamento Pequeno Em Prata")
    character = create_character(db_session, campaign.id, "Logan")
    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    deposit(db_session, holding, 1000, reason="saldo inicial de teste")

    proposal = _proposal("Cinco Pratas são entregues ao vendedor.", character_id=character.id)

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
