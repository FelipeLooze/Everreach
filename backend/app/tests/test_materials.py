import pytest

from app.core.enums import ItemQuality, ItemType, ItemWearSeverity
from app.game.character.service import create_character
from app.game.inventory.service import add_item, get_or_create_item, list_inventory
from app.game.items.durability import apply_item_wear
from app.game.items.encumbrance import get_carried_weight
from app.game.items.materials import (
    MaterialError,
    create_material_definition,
    get_material_definition,
    seed_core_materials,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session):
    campaign = create_campaign(db_session, "Materials")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session, campaign.id, "Hero", region.id, location.id
    )
    return campaign, character


def test_core_material_catalog_is_idempotent_and_extensible(db_session):
    first = seed_core_materials(db_session)
    second = seed_core_materials(db_session)
    moonsteel = create_material_definition(
        db_session,
        key="MOONSTEEL",
        name="Aço Lunar",
        weight_factor=0.6,
        wear_resistance=2.0,
        description="Liga fantástica leve e resistente.",
    )

    assert len(first) == len(second) == 7
    assert [row.id for row in first] == [row.id for row in second]
    assert get_material_definition(db_session, "moonsteel") is moonsteel
    assert moonsteel.weight_factor == 0.6
    assert moonsteel.wear_resistance == 2.0
    with pytest.raises(MaterialError, match="different canonical"):
        create_material_definition(
            db_session,
            key="MOONSTEEL",
            name="Aço Lunar",
            weight_factor=1.0,
            wear_resistance=2.0,
        )


def test_material_changes_effective_weight_and_stack_identity(db_session):
    _campaign, character = _character(db_session)
    seed_core_materials(db_session)
    get_or_create_item(db_session, "Tábuas", ItemType.MATERIAL.value, base_weight=10)
    wood = add_item(
        db_session, character.id, "Tábuas", quantity=2, material_key="WOOD"
    )
    iron = add_item(
        db_session, character.id, "Tábuas", quantity=1, material_key="IRON"
    )
    more_wood = add_item(
        db_session, character.id, "Tábuas", quantity=1, material_key="WOOD"
    )

    assert more_wood.id == wood.id
    assert wood.quantity == 3
    assert iron.id != wood.id
    assert len(list_inventory(db_session, character.id)) == 2
    assert get_carried_weight(db_session, character.id) == 22.0


def test_material_wear_resistance_is_consumed_by_durability(db_session):
    _campaign, character = _character(db_session)
    seed_core_materials(db_session)
    get_or_create_item(db_session, "Picareta de Ferro", ItemType.TOOL.value)
    get_or_create_item(db_session, "Picareta de Aço", ItemType.TOOL.value)
    iron = add_item(
        db_session,
        character.id,
        "Picareta de Ferro",
        quality=ItemQuality.STANDARD,
        material_key="IRON",
    )
    steel = add_item(
        db_session,
        character.id,
        "Picareta de Aço",
        quality=ItemQuality.STANDARD,
        material_key="STEEL",
    )

    iron_wear = apply_item_wear(
        db_session,
        iron,
        wear_key="impact:1",
        severity=ItemWearSeverity.MODERATE,
        cause="struck hard rock",
    )
    steel_wear = apply_item_wear(
        db_session,
        steel,
        wear_key="impact:1",
        severity=ItemWearSeverity.MODERATE,
        cause="struck hard rock",
    )

    assert iron_wear.record.wear_amount == 15
    assert steel_wear.record.wear_amount == 12
    assert steel.durability_current > iron.durability_current


def test_unknown_material_cannot_be_attached_to_item(db_session):
    _campaign, character = _character(db_session)
    with pytest.raises(ValueError, match="Material definition does not exist"):
        add_item(db_session, character.id, "Objeto", material_key="UNKNOWN")


def test_inventory_api_shows_material_name_and_effective_weight(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Material API"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Hero"}
    ).json()
    seed_core_materials(db_session)
    get_or_create_item(db_session, "Tábuas", ItemType.MATERIAL.value, base_weight=10)
    instance = add_item(
        db_session,
        character["id"],
        "Tábuas",
        quantity=2,
        material_key="WOOD",
    )

    response = client.get(
        f"/api/campaigns/{campaign['id']}/inventory",
        params={"character_id": character["id"]},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["item_instance_id"] == instance.id
    assert item["material"] == {"key": "WOOD", "name": "Madeira"}
    assert item["unit_weight"] == 4.0
    assert item["total_weight"] == 8.0
    assert response.json()["total_weight"] == 8.0
