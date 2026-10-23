"""Phase 14 playable integration: real world content through production flow."""

from app.core.enums import ActionIntentType, CombatActorType, ItemLocationType, NPCActivity
from app.db.models.business import Business
from app.db.models.currency import CurrencyHolding
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.job import Job, JobApplication
from app.db.models.npc import NPC
from app.db.models.shop import Shop, ShopListing
from app.game.character.service import create_character
from app.game.economy.initial_content import ensure_initial_economy_for_campaign
from app.game.economy.local_economy import get_settlement_wealth
from app.game.economy.playable import build_economy_view
from app.game.engine import resolve_action
from app.game.professions.service import list_character_professions
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Economia Jogável")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    assert ensure_initial_economy_for_campaign(db_session, campaign.id)
    db_session.flush()
    return campaign, region, village, character


def test_initial_economy_has_real_businesses_stock_and_jobs_without_gifting_player_gear(db_session):
    campaign, _region, _village, character = _setup(db_session)

    assert db_session.query(Business).filter(Business.campaign_id == campaign.id).count() == 3
    assert db_session.query(Shop).filter(Shop.campaign_id == campaign.id).count() == 3
    assert db_session.query(Job).filter(Job.campaign_id == campaign.id).count() == 3
    assert db_session.query(ShopListing).count() > 0

    player_items = db_session.query(ItemInstance).filter(
        ItemInstance.campaign_id == campaign.id,
        ItemInstance.location_ref == character.id,
    ).all()
    assert player_items == []
    assert db_session.query(CurrencyHolding).filter(
        CurrencyHolding.owner_type == CombatActorType.CHARACTER.value,
        CurrencyHolding.owner_id == character.id,
    ).count() == 0

    stocked = db_session.query(ItemInstance).filter(
        ItemInstance.campaign_id == campaign.id,
        ItemInstance.location_type == ItemLocationType.NPC.value,
    ).all()
    assert stocked
    assert all(item.owner_ref == item.location_ref for item in stocked)


def test_job_wages_then_shop_purchase_work_through_real_action_engine(db_session, fake_llm):
    campaign, _region, _village, character = _setup(db_session)
    blacksmith = db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id, NPC.role == "ferreira"
    ).one()
    blacksmith.activity = NPCActivity.WORKING.value
    character.location_id = blacksmith.workplace_location_id
    db_session.flush()

    application = resolve_action(
        db_session,
        fake_llm,
        campaign.id,
        character.id,
        'Candidato-me ao trabalho "Ajudante de Ferreiro"',
    )
    assert application.intent_type == ActionIntentType.APPLY_JOB.value
    assert "contratado" in application.mechanical_summary
    assert db_session.query(JobApplication).filter(
        JobApplication.applicant_id == character.id,
        JobApplication.status == "ACTIVE",
    ).count() == 1

    first_shift = resolve_action(
        db_session,
        fake_llm,
        campaign.id,
        character.id,
        'Trabalho no emprego "Ajudante de Ferreiro"',
    )
    second_shift = resolve_action(
        db_session,
        fake_llm,
        campaign.id,
        character.id,
        'Trabalho no emprego "Ajudante de Ferreiro"',
    )
    assert first_shift.intent_type == ActionIntentType.WORK_JOB.value
    assert second_shift.intent_type == ActionIntentType.WORK_JOB.value

    view = build_economy_view(db_session, character)
    assert view["balance_bronze"] == 24
    assert list_character_professions(db_session, character.id)

    shop = db_session.query(Shop).filter(
        Shop.campaign_id == campaign.id,
        Shop.location_id == character.location_id,
    ).one()
    bought = resolve_action(
        db_session,
        fake_llm,
        campaign.id,
        character.id,
        f'Compro "Faca de Ferro" em "{shop.name}"',
    )
    assert bought.intent_type == ActionIntentType.BUY.value
    assert "18 Bronze" in bought.mechanical_summary
    assert build_economy_view(db_session, character)["balance_bronze"] == 6

    knife = db_session.query(ItemInstance).join(ItemDefinition).filter(
        ItemInstance.campaign_id == campaign.id,
        ItemInstance.location_ref == character.id,
        ItemDefinition.name == "Faca de Ferro",
    ).one()
    assert knife.owner_ref == character.id

    left = resolve_action(
        db_session,
        fake_llm,
        campaign.id,
        character.id,
        'Deixo o emprego "Ajudante de Ferreiro"',
    )
    assert left.intent_type == ActionIntentType.LEAVE_JOB.value
    assert db_session.query(JobApplication).filter(
        JobApplication.applicant_id == character.id,
        JobApplication.status == "ENDED",
    ).count() == 1


def test_economy_view_is_local_and_stack_purchase_moves_one_unit(db_session, fake_llm):
    campaign, _region, _village, character = _setup(db_session)
    innkeeper = db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id, NPC.role == "estalajadeiro"
    ).one()
    innkeeper.activity = NPCActivity.WORKING.value
    character.location_id = innkeeper.workplace_location_id
    db_session.flush()

    assert get_settlement_wealth(db_session, character.location_id).value == "POOR"

    view = build_economy_view(db_session, character)
    assert len(view["shops"]) == 1
    ration = next(row for row in view["shops"][0]["listings"] if row["name"] == "Ração de Viagem")
    assert ration["quantity"] == 6

    # Give exactly enough money through the real holding only for this focused
    # stock-splitting assertion; earning it is covered by the previous test.
    from app.game.economy.wallet import deposit, get_or_create_holding

    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    deposit(db_session, holding, 4, reason="Pagamento de teste.")
    shop_name = view["shops"][0]["name"]
    resolve_action(
        db_session, fake_llm, campaign.id, character.id,
        f'Compro "Ração de Viagem" em "{shop_name}"',
    )

    after = build_economy_view(db_session, character)
    ration_after = next(row for row in after["shops"][0]["listings"] if row["name"] == "Ração de Viagem")
    assert ration_after["quantity"] == 5
    carried = db_session.query(ItemInstance).join(ItemDefinition).filter(
        ItemInstance.location_ref == character.id,
        ItemDefinition.name == "Ração de Viagem",
    ).one()
    assert carried.quantity == 1
