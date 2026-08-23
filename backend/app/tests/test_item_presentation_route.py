"""Phase 21O — Visual Presentation Contracts (Item, via the existing
inventory route rather than a new one — see app/api/routes/inventory.py)."""

from app.game.character.service import create_character
from app.game.inventory.service import add_item, get_or_create_item
from app.game.visual.spec import set_stable_visual_traits, set_visual_asset_reference
from app.game.world.seed import create_campaign, seed_initial_region


def test_inventory_api_exposes_signature_ornamentation_when_established(client, db_session):
    campaign = create_campaign(db_session, "Apresentacao Item Com Ornamento", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    definition = get_or_create_item(db_session, "Lâmina do Lobo", item_type="weapon")
    set_stable_visual_traits(
        db_session, "item_definition", definition.id,
        {"signature_ornamentation": "punho em formato de cabeça de lobo"},
    )
    add_item(db_session, character.id, "Lâmina do Lobo")
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/inventory",
        params={"character_id": character.id},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["signature_ornamentation"] == "punho em formato de cabeça de lobo"


def test_inventory_api_omits_signature_ornamentation_for_an_ordinary_item(client, db_session):
    campaign = create_campaign(db_session, "Apresentacao Item Comum", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    get_or_create_item(db_session, "Espada Comum", item_type="weapon")
    add_item(db_session, character.id, "Espada Comum")
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/inventory",
        params={"character_id": character.id},
    )

    item = response.json()["items"][0]
    assert item["signature_ornamentation"] is None


def test_inventory_api_exposes_asset_ref_once_a_future_illustration_is_recorded(client, db_session):
    campaign = create_campaign(db_session, "Apresentacao Item Com Asset", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    definition = get_or_create_item(db_session, "Machado Ilustrado", item_type="weapon")
    set_visual_asset_reference(
        db_session, "item_definition", definition.id, "ITEM_ILLUSTRATION", "asset_abc123",
    )
    add_item(db_session, character.id, "Machado Ilustrado")
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/inventory",
        params={"character_id": character.id},
    )

    item = response.json()["items"][0]
    assert item["asset_ref"] == "asset_abc123"


def test_inventory_api_omits_asset_ref_for_an_ordinary_item(client, db_session):
    campaign = create_campaign(db_session, "Apresentacao Item Sem Asset", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    get_or_create_item(db_session, "Espada Sem Asset", item_type="weapon")
    add_item(db_session, character.id, "Espada Sem Asset")
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/inventory",
        params={"character_id": character.id},
    )

    item = response.json()["items"][0]
    assert item["asset_ref"] is None
