import json

import pytest

from app.core.enums import (
    BodyArea,
    CharacterAttributeKey,
    CharacterResourceKey,
    CombatActionType,
    CombatActorType,
    CombatDamageType,
    CombatRangeBand,
    EquipmentSlot,
    EventType,
    ItemType,
    PhysicalDamageProfile,
)
from app.db.models.combat import CombatParticipant
from app.db.models.defense import (
    ActorCombatDefense,
    ItemArmorProfile,
    ItemCombatProfile,
)
from app.db.models.event import WorldEvent
from app.db.models.item import Item
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.combat.actions import (
    AttackMechanics,
    resolve_attack,
    resolve_profiled_attack,
)
from app.game.combat.defense import (
    CombatDefenseError,
    configure_actor_combat_defense,
    configure_item_combat_profile,
    equip_combat_item,
    resolve_damage_mitigation,
    unequip_combat_item,
)
from app.game.combat.encounters import CombatantSpec, start_encounter
from app.game.combat.turns import roll_initiative
from app.game.inventory.service import add_item, get_or_create_item
from app.game.items.armor import (
    ArmorError,
    configure_item_armor_profile,
    get_armor_coverage,
    get_armor_physical_protections,
)
from app.game.items.equipment import configure_item_equipment_profile, equip_item
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign, seed_initial_region


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


def test_armor_profile_has_coverage_and_differentiated_physical_protection(db_session):
    _campaign, character, _enemy, _encounter, hero, _guardian = _setup(db_session)
    item = get_or_create_item(db_session, "Gibão reforçado", ItemType.ARMOR.value)
    configure_item_equipment_profile(
        db_session, item, allowed_slots={EquipmentSlot.TORSO}
    )
    profile = configure_item_armor_profile(
        db_session,
        item,
        coverage={BodyArea.TORSO, BodyArea.ARMS},
        physical_protections={
            PhysicalDamageProfile.SLASH: 4,
            PhysicalDamageProfile.PIERCE: 2,
            PhysicalDamageProfile.BLUNT: 1,
        },
    )
    entry = add_item(db_session, character.id, item.name)
    equip_item(db_session, entry, slot=EquipmentSlot.TORSO)

    assert db_session.get(ItemArmorProfile, item.id) is profile
    assert get_armor_coverage(profile) == {BodyArea.TORSO, BodyArea.ARMS}
    assert get_armor_physical_protections(profile)[PhysicalDamageProfile.SLASH] == 4
    assert resolve_damage_mitigation(
        db_session,
        hero,
        CombatDamageType.PHYSICAL,
        physical_damage_profile=PhysicalDamageProfile.SLASH,
        target_body_area=BodyArea.TORSO,
    ).armor == 4
    assert resolve_damage_mitigation(
        db_session,
        hero,
        CombatDamageType.PHYSICAL,
        physical_damage_profile=PhysicalDamageProfile.BLUNT,
        target_body_area=BodyArea.TORSO,
    ).armor == 1
    assert resolve_damage_mitigation(
        db_session,
        hero,
        CombatDamageType.PHYSICAL,
        physical_damage_profile=PhysicalDamageProfile.SLASH,
        target_body_area=BodyArea.HEAD,
    ).armor == 0


def test_armor_profile_rejects_non_armor_and_unwearable_coverage(db_session):
    item = get_or_create_item(db_session, "Caixa", ItemType.CONTAINER.value)
    configure_item_equipment_profile(db_session, item, allowed_slots={EquipmentSlot.BACK})
    with pytest.raises(ArmorError, match="Only ARMOR"):
        configure_item_armor_profile(
            db_session,
            item,
            coverage={BodyArea.TORSO},
            physical_protections={PhysicalDamageProfile.BLUNT: 1},
        )


def _setup(db_session):
    campaign = create_campaign(db_session, "Combat Defense")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    enemy = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Guardião",
        role="guardian",
        alive=True,
        hp_current=20,
        hp_max=20,
    )
    db_session.add(enemy)
    db_session.flush()
    encounter = start_encounter(
        db_session,
        campaign.id,
        location.id,
        (
            CombatantSpec(
                CombatActorType.CHARACTER,
                character.id,
                "heroes",
                range_band=CombatRangeBand.ENGAGED,
            ),
            CombatantSpec(
                CombatActorType.NPC,
                enemy.id,
                "guardians",
                range_band=CombatRangeBand.ENGAGED,
            ),
        ),
    )
    participants = {
        row.actor_id: row
        for row in db_session.query(CombatParticipant)
        .filter(CombatParticipant.encounter_id == encounter.id)
        .all()
    }
    return (
        campaign,
        character,
        enemy,
        encounter,
        participants[character.id],
        participants[enemy.id],
    )


def test_equipped_armor_reduces_physical_damage_and_persists_breakdown(db_session):
    campaign, character, enemy, encounter, hero, guardian = _setup(db_session)
    entry = add_item(db_session, character.id, "Cota de Malha")
    item = db_session.get(Item, entry.item_id)
    configure_item_combat_profile(
        db_session,
        item,
        slot=EquipmentSlot.BODY,
        armor_rating=3,
    )
    equip_combat_item(db_session, entry)
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))

    action = resolve_attack(
        db_session,
        encounter,
        guardian,
        hero,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="armor-hit",
        rng=SequenceRng(10, 4),
    ).action

    assert action.damage_type == CombatDamageType.PHYSICAL.value
    assert action.damage_before_mitigation == 4
    assert action.armor_mitigation == 3
    assert action.resistance_mitigation == 0
    assert action.damage_total == 1
    assert character.hp_current == 19
    assert enemy.stamina_current == 8
    damage_event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_DAMAGE_APPLIED.value)
        .one()
    )
    payload = json.loads(damage_event.payload_json)
    assert payload["damage_before_mitigation"] == 4
    assert payload["armor_mitigation"] == 3
    assert damage_event.campaign_id == campaign.id


def test_elemental_damage_ignores_armor_and_uses_matching_resistance(db_session):
    _campaign, _character, enemy, encounter, hero, guardian = _setup(db_session)
    configure_actor_combat_defense(
        db_session,
        CombatActorType.NPC,
        enemy.id,
        armor_rating=10,
        resistances={CombatDamageType.FIRE: 3},
    )
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_profiled_attack(
        db_session,
        encounter,
        hero,
        guardian,
        mechanics=AttackMechanics(
            action_type=CombatActionType.MELEE_ATTACK,
            attack_attribute=CharacterAttributeKey.STRENGTH,
            resource_key=CharacterResourceKey.STAMINA,
            resource_cost=2,
            base_damage_dice=1,
            damage_die_sides=10,
            damage_attribute=CharacterAttributeKey.STRENGTH,
            damage_type=CombatDamageType.FIRE,
        ),
        action_key="fire-strike",
        rng=SequenceRng(10, 8),
    ).action

    assert action.damage_before_mitigation == 8
    assert action.armor_mitigation == 0
    assert action.resistance_mitigation == 3
    assert action.damage_total == 5
    assert enemy.hp_current == 15


def test_mitigation_can_absorb_all_damage_without_killing_target(db_session):
    _campaign, _character, enemy, encounter, hero, guardian = _setup(db_session)
    configure_actor_combat_defense(
        db_session,
        CombatActorType.NPC,
        enemy.id,
        armor_rating=20,
    )
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    action = resolve_attack(
        db_session,
        encounter,
        hero,
        guardian,
        action_type=CombatActionType.MELEE_ATTACK,
        action_key="absorbed-hit",
        rng=SequenceRng(10, 6),
    ).action

    assert action.damage_before_mitigation == 6
    assert action.damage_total == 0
    assert action.lethal is False
    assert enemy.hp_current == 20
    assert guardian.active is True


def test_equipment_slots_prevent_stacking_and_unequipped_items_do_not_apply(
    db_session,
):
    _campaign, character, _enemy, _encounter, hero, _guardian = _setup(db_session)
    first = add_item(db_session, character.id, "Armadura de Couro")
    second = add_item(db_session, character.id, "Cota Reforçada")
    for entry, rating in ((first, 2), (second, 5)):
        configure_item_combat_profile(
            db_session,
            db_session.get(Item, entry.item_id),
            slot=EquipmentSlot.BODY,
            armor_rating=rating,
        )

    assert resolve_damage_mitigation(
        db_session,
        hero,
        CombatDamageType.PHYSICAL,
    ).armor == 0
    equip_combat_item(db_session, first)
    with pytest.raises(CombatDefenseError, match="already occupied"):
        equip_combat_item(db_session, second)
    unequip_combat_item(db_session, first)
    equip_combat_item(db_session, second)
    assert resolve_damage_mitigation(
        db_session,
        hero,
        CombatDamageType.PHYSICAL,
    ).armor == 5


def test_defense_profiles_are_validated_immutable_and_removed_with_campaign(
    db_session,
):
    campaign, _character, enemy, _encounter, _hero, _guardian = _setup(db_session)
    item = get_or_create_item(db_session, "Manto Ígneo", "armor")
    profile = configure_item_combat_profile(
        db_session,
        item,
        slot=EquipmentSlot.BODY,
        resistances={CombatDamageType.FIRE: 4},
    )
    assert configure_item_combat_profile(
        db_session,
        item,
        slot=EquipmentSlot.BODY,
        resistances={CombatDamageType.FIRE: 4},
    ).item_id == profile.item_id
    with pytest.raises(CombatDefenseError, match="different combat mechanics"):
        configure_item_combat_profile(
            db_session,
            item,
            slot=EquipmentSlot.HEAD,
            resistances={CombatDamageType.FIRE: 4},
        )
    with pytest.raises(CombatDefenseError, match="between 0 and 20"):
        configure_actor_combat_defense(
            db_session,
            CombatActorType.NPC,
            enemy.id,
            armor_rating=21,
        )
    configure_actor_combat_defense(
        db_session,
        CombatActorType.NPC,
        enemy.id,
        resistances={CombatDamageType.POISON: 2},
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(ActorCombatDefense).count() == 0
    assert db_session.query(ItemCombatProfile).count() == 1
