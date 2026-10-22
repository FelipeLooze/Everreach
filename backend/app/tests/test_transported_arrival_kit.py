from app.core.enums import EquipmentSlot, ItemLocationType, ItemType
from app.db.models.defense import ItemArmorProfile
from app.db.models.container import ItemContainerProfile
from app.db.models.item import ItemDefinition, ItemInstance
from app.game.character.service import create_character
from app.game.items.containers import list_container_contents
from app.game.players.arrival_kit import (
    TRANSPORTED_BACKPACK_NAME,
    TRANSPORTED_OUTFIT_APPEARANCE,
    TRANSPORTED_OUTFIT_NAME,
    grant_transported_arrival_kit,
    transported_appearance,
)
from app.game.world.seed import create_campaign


def _character(db_session):
    campaign = create_campaign(db_session, "Arrival Kit")
    character = create_character(db_session, campaign.id, "Hero")
    db_session.flush()
    return campaign, character


def test_arrival_kit_contains_only_equipped_clothing_and_empty_backpack(db_session):
    _campaign, character = _character(db_session)

    outfit, backpack = grant_transported_arrival_kit(db_session, character)

    assert outfit.definition.name == TRANSPORTED_OUTFIT_NAME
    assert outfit.definition.type == ItemType.MISC.value
    assert outfit.location_type == ItemLocationType.CHARACTER_EQUIPPED.value
    assert outfit.equipped_slot == EquipmentSlot.TORSO.value
    assert db_session.get(ItemArmorProfile, outfit.definition_id) is None

    assert backpack.definition.name == TRANSPORTED_BACKPACK_NAME
    assert backpack.definition.type == ItemType.CONTAINER.value
    assert backpack.location_type == ItemLocationType.CHARACTER_EQUIPPED.value
    assert backpack.equipped_slot == EquipmentSlot.BACK.value
    assert db_session.get(ItemContainerProfile, backpack.definition_id).weight_capacity == 12.0
    assert list_container_contents(db_session, backpack.id) == []

    carried_types = {
        definition.type
        for _instance, definition in (
            db_session.query(ItemInstance, ItemDefinition)
            .join(ItemDefinition, ItemDefinition.id == ItemInstance.definition_id)
            .filter(ItemInstance.location_ref == character.id)
            .all()
        )
    }
    assert carried_types == {ItemType.MISC.value, ItemType.CONTAINER.value}


def test_arrival_kit_grant_is_idempotent(db_session):
    _campaign, character = _character(db_session)
    outfit, backpack = grant_transported_arrival_kit(db_session, character)
    first_ids = {outfit.id, backpack.id}

    second = grant_transported_arrival_kit(db_session, character)

    assert second == ()
    assert {
        row.id
        for row in db_session.query(ItemInstance)
        .filter(ItemInstance.owner_ref == character.id)
        .all()
    } == first_ids


def test_transported_visual_canon_is_shared_without_replacing_physical_traits():
    description = transported_appearance("Mulher adulta, cabelos castanhos e olhos escuros.")

    assert description.startswith("Mulher adulta")
    assert TRANSPORTED_OUTFIT_APPEARANCE in description
    assert "mochila compacta" in description
