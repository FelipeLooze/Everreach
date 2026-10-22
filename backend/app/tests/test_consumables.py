import pytest

from app.core.enums import ItemInstanceMode, ItemLocationType, ItemType
from app.db.models.consumable import ItemConsumptionRecord
from app.game.character.service import create_character
from app.game.items.consumables import ConsumableError, configure_consumable_profile, use_consumable
from app.game.items.service import create_item_definition, create_item_instance, move_item_instance
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db):
    campaign = create_campaign(db, "Consumíveis")
    region, location = seed_initial_region(db, campaign.id)
    character = create_character(db, campaign.id, "Lia", region.id, location.id)
    definition = create_item_definition(
        db, key="pocao_teste", name="Poção de Teste",
        item_type=ItemType.CONSUMABLE, instance_mode=ItemInstanceMode.STACKABLE,
    )
    configure_consumable_profile(db, definition, hp_restore=8, mana_restore=3, use_minutes=1)
    instance = create_item_instance(db, definition, quantity=2)
    move_item_instance(db, instance, location_type=ItemLocationType.CHARACTER, location_ref=character.id)
    return campaign, character, instance


def test_consumable_restores_only_missing_resources_and_consumes_one(db_session):
    campaign, character, instance = _setup(db_session)
    character.hp_current = character.hp_max - 5
    character.mana_current = character.mana_max - 1

    result = use_consumable(db_session, campaign.id, character, instance.id, action_key="consume-1")

    assert result.effects["hp"] == 5
    assert result.effects["mana"] == 1
    assert instance.quantity == 1
    assert db_session.query(ItemConsumptionRecord).count() == 1


def test_consumable_retry_is_idempotent_even_after_last_instance_is_deleted(db_session):
    campaign, character, instance = _setup(db_session)
    instance.quantity = 1
    character.hp_current -= 4

    first = use_consumable(db_session, campaign.id, character, instance.id, action_key="same-use")
    second = use_consumable(db_session, campaign.id, character, instance.id, action_key="same-use")

    assert first.effects == second.effects
    assert second.replayed is True
    assert db_session.query(ItemConsumptionRecord).count() == 1


def test_consumable_is_not_wasted_when_every_effect_is_full(db_session):
    campaign, character, instance = _setup(db_session)
    with pytest.raises(ConsumableError, match="no effect"):
        use_consumable(db_session, campaign.id, character, instance.id, action_key="waste")
    assert instance.quantity == 2


def test_inventory_api_exposes_consumable_effects(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Consumable API"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Hero"}
    ).json()
    definition = create_item_definition(
        db_session, key="ration_api", name="Ração de Viagem",
        item_type=ItemType.CONSUMABLE, instance_mode=ItemInstanceMode.STACKABLE,
    )
    configure_consumable_profile(
        db_session, definition, hunger_restore=20, thirst_restore=5, use_minutes=2
    )
    instance = create_item_instance(db_session, definition, quantity=2)
    move_item_instance(
        db_session, instance, location_type=ItemLocationType.CHARACTER,
        location_ref=character["id"],
    )
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign['id']}/inventory",
        params={"character_id": character["id"]},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["consumable"] == {
        "hp_restore": 0.0,
        "mana_restore": 0.0,
        "stamina_restore": 0.0,
        "hunger_restore": 20.0,
        "thirst_restore": 5.0,
        "use_minutes": 2,
    }
