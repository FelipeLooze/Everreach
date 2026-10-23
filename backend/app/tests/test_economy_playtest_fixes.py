"""Phase 14 playtest (2026-10-23): what natural play broke in the economy."""

from app.ai.context_builder import build_context
from app.ai.conversational_act import is_price_question
from app.ai.intent_parser import Intent
from app.core.enums import ActionIntentType, CombatActorType, NPCActivity
from app.db.models.npc import NPC
from app.game import engine
from app.game.character.service import create_character
from app.game.economy.initial_content import ensure_initial_economy_for_campaign
from app.game.economy.playable import build_economy_view
from app.game.economy.wallet import deposit, get_or_create_holding
from app.game.engine import resolve_action
from app.game.game_state import build_game_state
from app.game.world.seed import create_campaign, seed_initial_region


def _at_work(db_session, role):
    campaign = create_campaign(db_session, "Economia Playtest")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    assert ensure_initial_economy_for_campaign(db_session, campaign.id)
    worker = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.role == role).one()
    worker.activity = NPCActivity.WORKING.value
    character.location_id = worker.workplace_location_id
    db_session.flush()
    return campaign, character


def _refined(text, intent_type=ActionIntentType.TALK):
    return engine._refine_explicit_economy_intent(Intent(type=intent_type, target=None, raw_text=text))


def test_spoken_lines_are_read_as_actions_not_as_item_names():
    assert _refined('"Aceito a vaga de ajudante."').target == "ajudante"
    assert _refined('"Quero comprar a faca de ferro."').target == "faca de ferro"
    assert _refined('Compro a "Faca de Ferro"').target == "Faca de Ferro"
    assert _refined('"Ouvi que precisa de ajudante. Quero o trabalho."').type == ActionIntentType.APPLY_JOB
    assert _refined("Tento forjar uma faca de ferro.", ActionIntentType.SKILL_CHECK).type == ActionIntentType.PRODUCE
    # "vendo" is also "seeing": an attempt is only re-read as production.
    assert _refined("Estou vendo a trilha e tento escalar.", ActionIntentType.SKILL_CHECK).type == ActionIntentType.SKILL_CHECK
    assert _refined("Quanto paga o trabalho?").type == ActionIntentType.TALK


def test_taking_the_only_job_here_without_naming_it(db_session, fake_llm):
    campaign, character = _at_work(db_session, "ferreira")

    hired = resolve_action(db_session, fake_llm, campaign.id, character.id, '"Tudo bem. Quero o trabalho."')

    assert hired.intent_type == ActionIntentType.APPLY_JOB.value
    assert "contratado" in hired.mechanical_summary


def test_selling_back_to_you_and_buying_two_things_at_once(db_session, fake_llm):
    campaign, character = _at_work(db_session, "estalajadeiro")
    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    deposit(db_session, holding, 20, reason="Pagamento de teste.")

    bought = resolve_action(
        db_session, fake_llm, campaign.id, character.id,
        '"Quero comprar a ração de viagem e a carne seca."',
    )
    assert "Ração de Viagem" in bought.mechanical_summary and "Carne Seca" in bought.mechanical_summary
    assert "Total pago, já entregue: 6 Bronze." in bought.mechanical_summary
    assert build_economy_view(db_session, character)["balance_bronze"] == 14

    sold = resolve_action(
        db_session, fake_llm, campaign.id, character.id, '"Vendo a carne seca de volta para você."'
    )
    assert sold.intent_type == ActionIntentType.SELL.value
    assert "vende 1× Carne Seca" in sold.mechanical_summary


def test_the_narrator_knows_real_wages_and_a_wage_question_is_grounded(db_session):
    campaign, character = _at_work(db_session, "ferreira")
    state = build_game_state(db_session, campaign.id, character.id)

    blacksmith = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.role == "ferreira").one()

    context = build_context(
        db_session, state, active_interlocutor=blacksmith.name,
        player_input="Quanto paga o trabalho de ajudante?",
    )

    assert "WORK IN THIS SETTLEMENT" in context
    assert "Ajudante de Ferreiro" in context and "12 bronze per shift of 3h" in context
    assert is_price_question("Quanto paga o trabalho de ajudante?")
    assert "CURRENT OFFER: 12 bronze." in context
    assert "12 bronze por turno de 3 horas" in context


def test_copying_a_turn_from_two_turns_ago_is_rejected_even_after_an_action():
    from app.ai import narrator

    refusal = "Wren Sernn mantém o martelo erguido. — Quatorze bronze. Não tem, não leva. O martelo desce."
    history = "\n".join([
        f'Resposta de Wren Sernn anteriormente: "{refusal}"',
        'Resposta narrada anteriormente: "O calor da forja envolve tudo; o turno termina e doze moedas pousam na mão."',
    ])

    violations = narrator._find_stale_repeated_response_violations(
        refusal, history, "Agora sim. Compro o martelo de trabalho."
    )

    assert violations and "AUTHORITATIVE MECHANICAL FACTS" in violations[0]
