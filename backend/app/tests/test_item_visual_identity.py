"""Phase 21D — Item Visual Identity."""

import pytest

from app.core.enums import ItemQuality
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.material import MaterialDefinition
from app.db.models.weapon import ItemWeaponProfile
from app.game.character.service import create_character
from app.game.inventory.service import add_item, get_or_create_item
from app.game.visual.item import ItemVisualIdentityError, build_item_visual_spec
from app.game.visual.spec import set_stable_visual_traits
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session):
    campaign = create_campaign(db_session, "Item Visual Identity")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, location.id)
    return campaign, character


def test_spec_derives_quality_and_default_condition_from_real_item_data(db_session):
    _campaign, character = _character(db_session)
    get_or_create_item(db_session, "Machado Comum", item_type="weapon")
    instance = add_item(db_session, character.id, "Machado Comum", quality=ItemQuality.GOOD)

    spec = build_item_visual_spec(db_session, instance.id)

    assert spec.name == "Machado Comum"
    assert spec.item_type == "WEAPON"
    assert spec.quality == "GOOD"


def test_spec_reflects_real_durability_derived_condition(db_session):
    _campaign, character = _character(db_session)
    get_or_create_item(db_session, "Espada Gasta", item_type="weapon")
    instance = add_item(db_session, character.id, "Espada Gasta")
    instance.durability_current = 30.0
    instance.durability_max = 100.0
    db_session.flush()

    spec = build_item_visual_spec(db_session, instance.id)

    assert spec.condition == "DAMAGED"


def test_spec_derives_weapon_family_from_the_real_weapon_profile(db_session):
    _campaign, character = _character(db_session)
    definition = get_or_create_item(db_session, "Espada Longa", item_type="weapon")
    db_session.add(
        ItemWeaponProfile(
            item_id=definition.id,
            weapon_family="SWORD",
            damage_profiles_json="[]",
            reach="NORMAL",
            hand_requirement="ONE_OR_TWO_HANDS",
        )
    )
    db_session.flush()
    instance = add_item(db_session, character.id, "Espada Longa")

    spec = build_item_visual_spec(db_session, instance.id)

    assert spec.weapon_family == "SWORD"


def test_spec_has_no_weapon_family_for_a_non_weapon_item(db_session):
    _campaign, character = _character(db_session)
    get_or_create_item(db_session, "Ração de Viagem", item_type="consumable")
    instance = add_item(db_session, character.id, "Ração de Viagem")

    spec = build_item_visual_spec(db_session, instance.id)

    assert spec.weapon_family is None


def test_spec_derives_material_name_from_the_real_material_definition(db_session):
    _campaign, character = _character(db_session)
    material = MaterialDefinition(
        key="STEEL", name="Aço", weight_factor=1.0, wear_resistance=1.0,
    )
    db_session.add(material)
    db_session.flush()
    get_or_create_item(db_session, "Adaga de Aço", item_type="weapon")
    instance = add_item(db_session, character.id, "Adaga de Aço", material_key="steel")

    spec = build_item_visual_spec(db_session, instance.id)

    assert spec.material == "Aço"


def test_ordinary_item_has_no_signature_ornamentation_by_default(db_session):
    """The literal expression of 'ordinary items should look ordinary'."""
    _campaign, character = _character(db_session)
    get_or_create_item(db_session, "Espada de Ferro Comum", item_type="weapon")
    instance = add_item(db_session, character.id, "Espada de Ferro Comum")

    spec = build_item_visual_spec(db_session, instance.id)

    assert spec.signature_ornamentation is None


def test_signature_ornamentation_surfaces_once_explicitly_established_as_canon(db_session):
    _campaign, character = _character(db_session)
    definition = get_or_create_item(db_session, "Lâmina do Lobo", item_type="weapon")
    instance = add_item(db_session, character.id, "Lâmina do Lobo")
    set_stable_visual_traits(
        db_session, "item_definition", definition.id,
        {"signature_ornamentation": "punho em formato de cabeça de lobo"},
    )

    spec = build_item_visual_spec(db_session, instance.id)

    assert spec.signature_ornamentation == "punho em formato de cabeça de lobo"


def test_signature_ornamentation_is_shared_by_every_instance_of_the_same_definition(db_session):
    """Item definitions are campaign-global (Phase 10) — the ornament
    is Canon about the item TYPE, not any one physical copy."""
    _campaign, character = _character(db_session)
    definition = get_or_create_item(db_session, "Machado Rúnico", item_type="weapon")
    set_stable_visual_traits(
        db_session, "item_definition", definition.id, {"signature_ornamentation": "runas na lâmina"},
    )
    first = add_item(db_session, character.id, "Machado Rúnico")
    second = add_item(db_session, character.id, "Machado Rúnico")

    assert build_item_visual_spec(db_session, first.id).signature_ornamentation == "runas na lâmina"
    assert build_item_visual_spec(db_session, second.id).signature_ornamentation == "runas na lâmina"


def test_raises_for_a_nonexistent_item_instance(db_session):
    with pytest.raises(ItemVisualIdentityError):
        build_item_visual_spec(db_session, "item_instance_nao_existe")
