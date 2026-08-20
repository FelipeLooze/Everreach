import pytest
from sqlalchemy.exc import IntegrityError

from app.core.enums import ItemInstanceMode, ItemQuality, ItemType
from app.db.models.item import ItemDefinition, ItemInstance
from app.game.items.service import (
    ItemFoundationError,
    create_item_definition,
    create_item_instance,
    get_item_definition,
    item_key_from_name,
)


def test_definition_and_physical_instances_are_distinct_persistent_entities(
    db_session,
):
    definition = create_item_definition(
        db_session,
        key="flecha_comum",
        name="Flecha Comum",
        item_type=ItemType.AMMUNITION,
        instance_mode=ItemInstanceMode.STACKABLE,
        description="Uma flecha comum e intercambiável.",
    )
    first_stack = create_item_instance(db_session, definition, quantity=20)
    second_stack = create_item_instance(db_session, definition, quantity=8)

    assert definition.id != first_stack.id
    assert first_stack.id != second_stack.id
    assert first_stack.definition_id == definition.id
    assert first_stack.quantity == 20
    assert second_stack.quantity == 8
    assert get_item_definition(db_session, "FLECHA_COMUM").id == definition.id
    assert db_session.query(ItemDefinition).count() == 1
    assert db_session.query(ItemInstance).count() == 2


def test_unique_definition_creates_distinct_objects_and_never_a_quantity_stack(
    db_session,
):
    definition = create_item_definition(
        db_session,
        key="espada_longa",
        name="Espada Longa",
        item_type=ItemType.WEAPON,
        instance_mode=ItemInstanceMode.UNIQUE,
    )
    first_sword = create_item_instance(db_session, definition)
    second_sword = create_item_instance(db_session, definition)

    assert first_sword.id != second_sword.id
    assert first_sword.quantity == second_sword.quantity == 1
    with pytest.raises(ItemFoundationError, match="quantity 1"):
        create_item_instance(db_session, definition, quantity=2)


def test_quality_is_instance_craftsmanship_not_definition_rarity(db_session):
    definition = create_item_definition(
        db_session,
        key="faca_de_trabalho",
        name="Faca de Trabalho",
        item_type=ItemType.TOOL,
        instance_mode=ItemInstanceMode.UNIQUE,
    )
    standard = create_item_instance(db_session, definition)
    masterwork = create_item_instance(
        db_session, definition, quality=ItemQuality.MASTERWORK
    )

    assert standard.quality == ItemQuality.STANDARD.value
    assert masterwork.quality == ItemQuality.MASTERWORK.value
    assert not hasattr(definition, "rarity")
    with pytest.raises(ItemFoundationError, match="Invalid item quality"):
        create_item_instance(db_session, definition, quality="EPIC")


def test_item_definitions_are_idempotent_but_canonical_data_is_immutable(db_session):
    definition = create_item_definition(
        db_session,
        key="moeda_de_cobre",
        name="Moeda de Cobre",
        item_type=ItemType.CURRENCY,
        instance_mode=ItemInstanceMode.STACKABLE,
    )
    same = create_item_definition(
        db_session,
        key="moeda_de_cobre",
        name="Moeda de Cobre",
        item_type=ItemType.CURRENCY,
        instance_mode=ItemInstanceMode.STACKABLE,
    )

    assert same.id == definition.id
    with pytest.raises(ItemFoundationError, match="different canonical data"):
        create_item_definition(
            db_session,
            key="moeda_de_cobre",
            name="Moeda de Ouro",
            item_type=ItemType.CURRENCY,
            instance_mode=ItemInstanceMode.STACKABLE,
        )
    assert item_key_from_name("Poção Básica") == "pocao_basica"


def test_item_weight_is_non_negative_and_part_of_canonical_definition(db_session):
    definition = create_item_definition(
        db_session,
        key="lingote_de_ferro",
        name="Lingote de Ferro",
        item_type=ItemType.MATERIAL,
        instance_mode=ItemInstanceMode.STACKABLE,
        base_weight=2.5,
    )

    assert definition.base_weight == 2.5
    with pytest.raises(ItemFoundationError, match="non-negative"):
        create_item_definition(
            db_session,
            key="peso_impossivel",
            name="Peso Impossível",
            item_type=ItemType.MATERIAL,
            instance_mode=ItemInstanceMode.STACKABLE,
            base_weight=-1,
        )
    with pytest.raises(ItemFoundationError, match="different canonical data"):
        create_item_definition(
            db_session,
            key="lingote_de_ferro",
            name="Lingote de Ferro",
            item_type=ItemType.MATERIAL,
            instance_mode=ItemInstanceMode.STACKABLE,
            base_weight=3.0,
        )


def test_instance_quantity_is_protected_by_service_and_database(db_session):
    definition = create_item_definition(
        db_session,
        key="trigo",
        name="Trigo",
        item_type=ItemType.MATERIAL,
        instance_mode=ItemInstanceMode.STACKABLE,
    )
    with pytest.raises(ItemFoundationError, match="positive integer"):
        create_item_instance(db_session, definition, quantity=0)

    db_session.add(ItemInstance(definition_id=definition.id, quantity=0))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
