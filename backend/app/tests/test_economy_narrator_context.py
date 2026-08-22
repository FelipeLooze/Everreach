"""Phase 14N — System / Narrator Context. Closes Phase 14 (14A-14N).

CURRENCY always shows the character's own real carried money, in
denominations. LOCAL ECONOMY surfaces settlement wealth as a texture
hint (never a price). NEARBY SHOPS only shows shops physically at the
character's location, with only their real stock and priced listings —
never internal till/specialization data.
"""

from app.ai import context_builder
from app.core.enums import (
    CombatActorType,
    ItemType,
    SettlementWealthBand,
    ShopStatus,
)
from app.game.character.service import create_character
from app.game.economy.local_economy import set_settlement_wealth
from app.game.economy.pricing import set_item_base_value
from app.game.economy.shops import create_shop, stock_item
from app.game.economy.wallet import deposit, get_or_create_holding
from app.game.game_state import build_game_state
from app.game.inventory.service import add_item, get_or_create_item
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Economy Narrator Context")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, village, character


def test_currency_section_shows_the_characters_own_denominations(db_session):
    campaign, region, village, character = _setup(db_session)
    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    deposit(db_session, holding, 25_430, reason="Fortuna acumulada.")

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    section = context.split("CURRENCY", 1)[1].split("LOCAL ECONOMY", 1)[0]
    assert "Gold: 2" in section
    assert "Silver: 54" in section
    assert "Bronze: 30" in section


def test_currency_section_shows_zero_with_no_holding(db_session):
    campaign, region, village, character = _setup(db_session)

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    section = context.split("CURRENCY", 1)[1].split("LOCAL ECONOMY", 1)[0]
    assert "Gold: 0" in section
    assert "Silver: 0" in section
    assert "Bronze: 0" in section


def test_local_economy_flags_gold_as_unusual_outside_wealthy_settlements(db_session):
    campaign, region, village, character = _setup(db_session)

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    section = context.split("LOCAL ECONOMY", 1)[1].split("NEARBY SHOPS", 1)[0]
    assert "Settlement wealth: POOR" in section
    assert "unusual here" in section


def test_local_economy_marks_gold_as_routine_in_a_wealthy_settlement(db_session):
    campaign, region, village, character = _setup(db_session)
    set_settlement_wealth(db_session, campaign.id, village.id, SettlementWealthBand.WEALTHY)

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    section = context.split("LOCAL ECONOMY", 1)[1].split("NEARBY SHOPS", 1)[0]
    assert "circulate routinely" in section


def test_nearby_shops_shows_open_shop_stock_and_prices(db_session):
    campaign, region, village, character = _setup(db_session)
    operator = create_character(db_session, campaign.id, "Merchant", region.id, village.id)
    shop = create_shop(
        db_session, campaign.id, "Ferraria de Cardal", CombatActorType.CHARACTER, operator.id,
        location_id=village.id,
    )
    definition = get_or_create_item(db_session, "Machado de Ferro", "TOOL")
    set_item_base_value(db_session, definition, 40)
    axe = add_item(db_session, operator.id, "Machado de Ferro")
    stock_item(db_session, shop, axe)

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    section = context.split("NEARBY SHOPS", 1)[1]
    assert "Ferraria de Cardal [open]" in section
    assert "Machado de Ferro: 40 bronze" in section
    assert "till" not in section.lower()


def test_closed_shop_hides_its_stock(db_session):
    campaign, region, village, character = _setup(db_session)
    operator = create_character(db_session, campaign.id, "Merchant", region.id, village.id)
    shop = create_shop(
        db_session, campaign.id, "Loja Fechada", CombatActorType.CHARACTER, operator.id,
        location_id=village.id,
    )
    shop.status = ShopStatus.CLOSED
    definition = get_or_create_item(db_session, "Prego", "TOOL")
    set_item_base_value(db_session, definition, 2)
    nail = add_item(db_session, operator.id, "Prego")
    stock_item(db_session, shop, nail)
    db_session.flush()

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    section = context.split("NEARBY SHOPS", 1)[1]
    assert "Loja Fechada [closed]" in section
    assert "Prego" not in section


def test_no_shops_at_this_location_shows_none(db_session):
    campaign, region, village, character = _setup(db_session)

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    section = context.split("NEARBY SHOPS", 1)[1]
    assert "- none" in section.split("\n\n")[0]
