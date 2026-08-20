import pytest

from app.core.enums import EquipmentSlot, ItemLocationType, ItemType
from app.game.character.service import create_character
from app.game.inventory.service import add_item, get_or_create_item, list_inventory
from app.game.items.containers import (
    ContainerError,
    configure_item_container_profile,
    get_container_content_weight,
    store_item_in_container,
)
from app.game.items.encumbrance import get_carried_weight
from app.game.items.equipment import (
    configure_item_equipment_profile,
    equip_item,
    resolve_item_accessibility,
)
from app.game.items.service import move_item_instance
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session):
    campaign = create_campaign(db_session, "Containers")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session, campaign.id, "Hero", region.id, location.id
    )
    return campaign, character


def _container(db_session, character, name, weight=1.0, capacity=20.0):
    definition = get_or_create_item(
        db_session, name, ItemType.CONTAINER.value, base_weight=weight
    )
    configure_item_container_profile(
        db_session, definition, weight_capacity=capacity
    )
    return add_item(db_session, character.id, name)


def test_container_profile_is_validated_and_canonical(db_session):
    definition = get_or_create_item(db_session, "Mochila", ItemType.CONTAINER.value)
    first = configure_item_container_profile(
        db_session, definition, weight_capacity=15
    )
    assert configure_item_container_profile(
        db_session, definition, weight_capacity=15
    ) is first
    with pytest.raises(ContainerError, match="different canonical"):
        configure_item_container_profile(db_session, definition, weight_capacity=20)
    ordinary = get_or_create_item(db_session, "Pedra", ItemType.MATERIAL.value)
    with pytest.raises(ContainerError, match="Only CONTAINER"):
        configure_item_container_profile(db_session, ordinary, weight_capacity=1)


def test_nested_containers_preserve_inventory_and_count_weight_once(db_session):
    _campaign, character = _character(db_session)
    backpack = _container(db_session, character, "Mochila", weight=2, capacity=20)
    pouch = _container(db_session, character, "Bolsa", weight=1, capacity=10)
    herbs = add_item(db_session, character.id, "Ervas", quantity=3, base_weight=0.5)

    store_item_in_container(db_session, herbs, pouch)
    store_item_in_container(db_session, pouch, backpack)

    assert herbs.location_type == ItemLocationType.CONTAINER.value
    assert herbs.owner_ref == character.id
    assert get_container_content_weight(db_session, pouch) == 1.5
    assert get_container_content_weight(db_session, backpack) == 2.5
    assert get_carried_weight(db_session, character.id) == 4.5
    assert {entry.id for entry in list_inventory(db_session, character.id)} == {
        backpack.id, pouch.id, herbs.id
    }


def test_container_rejects_cycles_and_capacity_overflow(db_session):
    _campaign, character = _character(db_session)
    first = _container(db_session, character, "Primeira bolsa", capacity=5)
    second = _container(db_session, character, "Segunda bolsa", capacity=5)
    stone = add_item(db_session, character.id, "Pedra", base_weight=6)

    store_item_in_container(db_session, second, first)
    with pytest.raises(ContainerError, match="recursive cycle"):
        store_item_in_container(db_session, first, second)
    with pytest.raises(ContainerError, match="cannot contain itself"):
        store_item_in_container(db_session, first, first)
    with pytest.raises(ContainerError, match="capacity"):
        store_item_in_container(db_session, stone, first)


def test_nested_addition_also_respects_outer_container_capacity(db_session):
    _campaign, character = _character(db_session)
    backpack = _container(db_session, character, "Mochila pequena", capacity=3)
    pouch = _container(db_session, character, "Bolsa ampla", capacity=20)
    cargo = add_item(db_session, character.id, "Carga", base_weight=3)
    store_item_in_container(db_session, pouch, backpack)

    with pytest.raises(ContainerError, match="capacity"):
        store_item_in_container(db_session, cargo, pouch)


def test_waist_container_makes_direct_content_quick_but_nested_content_stowed(
    db_session,
):
    _campaign, character = _character(db_session)
    pouch = _container(db_session, character, "Bolsa de cintura", capacity=10)
    bottle = _container(db_session, character, "Frasco", capacity=3)
    herb = add_item(db_session, character.id, "Folha", base_weight=0.1)
    configure_item_equipment_profile(
        db_session, pouch.definition, allowed_slots={EquipmentSlot.WAIST}
    )
    equip_item(db_session, pouch, slot=EquipmentSlot.WAIST)
    store_item_in_container(db_session, bottle, pouch)
    store_item_in_container(db_session, herb, bottle)

    assert resolve_item_accessibility(db_session, bottle).value == "QUICK"
    assert resolve_item_accessibility(db_session, herb).value == "STOWED"
    with pytest.raises(ValueError, match="authoritative container"):
        move_item_instance(
            db_session,
            herb,
            location_type=ItemLocationType.CONTAINER,
            location_ref=pouch.id,
        )


def test_inventory_api_exposes_container_hierarchy(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Container API"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Hero"}
    ).json()
    backpack = _container(db_session, type("C", (), {"id": character["id"]})(), "Mochila", capacity=12)
    ration = add_item(db_session, character["id"], "Ração", base_weight=1)
    store_item_in_container(db_session, ration, backpack)

    response = client.get(
        f"/api/campaigns/{campaign['id']}/inventory",
        params={"character_id": character["id"]},
    )

    assert response.status_code == 200
    by_id = {item["item_instance_id"]: item for item in response.json()["items"]}
    assert by_id[backpack.id]["container"] == {
        "weight_capacity": 12.0,
        "content_weight": 1.0,
    }
    assert by_id[ration.id]["contained_in_item_instance_id"] == backpack.id
    assert by_id[ration.id]["contained_in_name"] == "Mochila"
