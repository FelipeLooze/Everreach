import json

import pytest

from app.core.enums import (
    CombatActionType,
    CombatActorType,
    CombatDamageType,
    CombatRangeBand,
    EquipmentSlot,
    EventType,
    PhysicalDamageProfile,
    WeaponFamily,
    WeaponHandRequirement,
    WeaponReach,
)
from app.db.models.combat import CombatParticipant
from app.db.models.event import WorldEvent
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.combat.actions import CombatActionError
from app.game.combat.encounters import CombatantSpec, start_encounter
from app.game.combat.turns import roll_initiative
from app.game.inventory.service import add_item, get_or_create_item
from app.game.items.equipment import (
    configure_item_equipment_profile,
    equip_item,
    unequip_item,
)
from app.game.items.weapons import (
    WeaponError,
    configure_item_weapon_profile,
    get_weapon_damage_profiles,
    resolve_weapon_attack,
)
from app.game.world.seed import create_campaign, seed_initial_region


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


class ExplodingRng:
    def randint(self, _minimum: int, _maximum: int) -> int:
        raise AssertionError("A replay must not roll again.")


def _combat(db_session, target_range=CombatRangeBand.ENGAGED):
    campaign = create_campaign(db_session, "Weapons")
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
        name="Alvo",
        alive=True,
    )
    db_session.add(enemy)
    db_session.flush()
    encounter = start_encounter(
        db_session,
        campaign.id,
        location.id,
        (
            CombatantSpec(CombatActorType.CHARACTER, character.id, "heroes"),
            CombatantSpec(
                CombatActorType.NPC,
                enemy.id,
                "enemies",
                range_band=target_range,
            ),
        ),
    )
    participants = {
        row.actor_id: row
        for row in db_session.query(CombatParticipant)
        .filter(CombatParticipant.encounter_id == encounter.id)
        .all()
    }
    return character, encounter, participants[character.id], participants[enemy.id]


def _weapon(
    db_session,
    character_id,
    *,
    name="Espada Longa",
    family=WeaponFamily.SWORD,
    damage_profiles=None,
    reach=WeaponReach.NORMAL,
    hand_requirement=WeaponHandRequirement.ONE_OR_TWO_HANDS,
    allowed_slots=None,
    active_slot=EquipmentSlot.MAIN_HAND,
):
    definition = get_or_create_item(db_session, name, "weapon")
    configure_item_equipment_profile(
        db_session,
        definition,
        allowed_slots=allowed_slots
        or {
            EquipmentSlot.MAIN_HAND,
            EquipmentSlot.BOTH_HANDS,
            EquipmentSlot.WAIST,
        },
    )
    profile = configure_item_weapon_profile(
        db_session,
        definition,
        weapon_family=family,
        damage_profiles=damage_profiles
        or {PhysicalDamageProfile.SLASH, PhysicalDamageProfile.PIERCE},
        reach=reach,
        hand_requirement=hand_requirement,
    )
    instance = add_item(db_session, character_id, name)
    equip_item(db_session, instance, slot=active_slot)
    return profile, instance


def test_weapon_profile_is_validated_immutable_and_has_no_generic_bonuses(db_session):
    character, _encounter, _hero, _enemy = _combat(db_session)
    profile, _instance = _weapon(db_session, character.id)

    assert profile.weapon_family == WeaponFamily.SWORD.value
    assert profile.reach == WeaponReach.NORMAL.value
    assert profile.hand_requirement == WeaponHandRequirement.ONE_OR_TWO_HANDS.value
    assert get_weapon_damage_profiles(profile) == {
        PhysicalDamageProfile.SLASH,
        PhysicalDamageProfile.PIERCE,
    }
    assert not hasattr(profile, "attack_bonus")
    assert not hasattr(profile, "balance")

    with pytest.raises(WeaponError, match="different canonical"):
        configure_item_weapon_profile(
            db_session,
            profile.item,
            weapon_family=WeaponFamily.AXE,
            damage_profiles={PhysicalDamageProfile.SLASH},
            reach=WeaponReach.NORMAL,
            hand_requirement=WeaponHandRequirement.ONE_OR_TWO_HANDS,
        )


def test_weapon_configuration_requires_weapon_category_and_compatible_hands(db_session):
    character, _encounter, _hero, _enemy = _combat(db_session)
    backpack = get_or_create_item(db_session, "Mochila", "container")
    configure_item_equipment_profile(
        db_session,
        backpack,
        allowed_slots={EquipmentSlot.BACK},
    )
    with pytest.raises(WeaponError, match="Only WEAPON"):
        configure_item_weapon_profile(
            db_session,
            backpack,
            weapon_family=WeaponFamily.CLUB,
            damage_profiles={PhysicalDamageProfile.BLUNT},
            reach=WeaponReach.NORMAL,
            hand_requirement=WeaponHandRequirement.ONE_HAND,
        )

    greatsword = get_or_create_item(db_session, "Montante", "weapon")
    configure_item_equipment_profile(
        db_session,
        greatsword,
        allowed_slots={EquipmentSlot.MAIN_HAND, EquipmentSlot.BACK},
    )
    with pytest.raises(WeaponError, match="hand requirement"):
        configure_item_weapon_profile(
            db_session,
            greatsword,
            weapon_family=WeaponFamily.SWORD,
            damage_profiles={PhysicalDamageProfile.SLASH},
            reach=WeaponReach.LONG,
            hand_requirement=WeaponHandRequirement.TWO_HANDS,
        )
    assert character.id


def test_weapon_attack_persists_selected_instance_and_damage_profile(db_session):
    character, encounter, hero, enemy = _combat(db_session)
    _profile, sword = _weapon(db_session, character.id)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    result = resolve_weapon_attack(
        db_session,
        encounter,
        hero,
        enemy,
        weapon_instance_id=sword.id,
        action_type=CombatActionType.MELEE_ATTACK,
        damage_profile=PhysicalDamageProfile.PIERCE,
        action_key="sword-thrust",
        rng=SequenceRng(10, 2),
    )

    assert result.action.weapon_instance_id == sword.id
    assert result.action.physical_damage_profile == PhysicalDamageProfile.PIERCE.value
    assert result.action.damage_type == CombatDamageType.PHYSICAL.value
    assert result.action.attack_modifier == 0
    payload = json.loads(
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.COMBAT_ACTION_RESOLVED.value)
        .one()
        .payload_json
    )
    assert payload["weapon_instance_id"] == sword.id
    assert payload["physical_damage_profile"] == "PIERCE"

    unequip_item(db_session, sword)
    replay = resolve_weapon_attack(
        db_session,
        encounter,
        hero,
        enemy,
        weapon_instance_id=sword.id,
        action_type=CombatActionType.MELEE_ATTACK,
        damage_profile=PhysicalDamageProfile.PIERCE,
        action_key="sword-thrust",
        rng=ExplodingRng(),
    )
    assert replay.replayed is True
    with pytest.raises(CombatActionError, match="another combat action"):
        resolve_weapon_attack(
            db_session,
            encounter,
            hero,
            enemy,
            weapon_instance_id=sword.id,
            action_type=CombatActionType.MELEE_ATTACK,
            damage_profile=PhysicalDamageProfile.SLASH,
            action_key="sword-thrust",
        )


def test_player_selects_damage_mode_and_weapon_must_be_ready_in_hand(db_session):
    character, encounter, hero, enemy = _combat(db_session)
    _profile, sword = _weapon(db_session, character.id)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    with pytest.raises(WeaponError, match="does not support"):
        resolve_weapon_attack(
            db_session,
            encounter,
            hero,
            enemy,
            weapon_instance_id=sword.id,
            action_type=CombatActionType.MELEE_ATTACK,
            damage_profile=PhysicalDamageProfile.BLUNT,
            action_key="unsupported-blunt",
        )

    equip_item(db_session, sword, slot=EquipmentSlot.WAIST)
    with pytest.raises(WeaponError, match="immediately usable"):
        resolve_weapon_attack(
            db_session,
            encounter,
            hero,
            enemy,
            weapon_instance_id=sword.id,
            action_type=CombatActionType.MELEE_ATTACK,
            damage_profile=PhysicalDamageProfile.SLASH,
            action_key="sheathed-sword",
        )


def test_weapon_reach_is_consumed_by_combat_without_choosing_the_action(db_session):
    character, encounter, hero, enemy = _combat(
        db_session,
        target_range=CombatRangeBand.NEAR,
    )
    _profile, spear = _weapon(
        db_session,
        character.id,
        name="Lança",
        family=WeaponFamily.SPEAR,
        damage_profiles={PhysicalDamageProfile.PIERCE},
        reach=WeaponReach.LONG,
        hand_requirement=WeaponHandRequirement.TWO_HANDS,
        allowed_slots={EquipmentSlot.BOTH_HANDS, EquipmentSlot.BACK},
        active_slot=EquipmentSlot.BOTH_HANDS,
    )
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    result = resolve_weapon_attack(
        db_session,
        encounter,
        hero,
        enemy,
        weapon_instance_id=spear.id,
        action_type=CombatActionType.MELEE_ATTACK,
        damage_profile=PhysicalDamageProfile.PIERCE,
        action_key="long-reach-thrust",
        rng=SequenceRng(10, 1),
    )
    assert result.action.target_range_band == CombatRangeBand.NEAR.value


def test_ranged_weapon_requires_explicit_ranged_action_and_respects_far_range(db_session):
    character, encounter, hero, enemy = _combat(
        db_session,
        target_range=CombatRangeBand.FAR,
    )
    _profile, bow = _weapon(
        db_session,
        character.id,
        name="Arco",
        family=WeaponFamily.BOW,
        damage_profiles={PhysicalDamageProfile.PIERCE},
        reach=WeaponReach.RANGED,
        hand_requirement=WeaponHandRequirement.TWO_HANDS,
        allowed_slots={EquipmentSlot.BOTH_HANDS, EquipmentSlot.BACK},
        active_slot=EquipmentSlot.BOTH_HANDS,
    )
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    with pytest.raises(WeaponError, match="attack type"):
        resolve_weapon_attack(
            db_session,
            encounter,
            hero,
            enemy,
            weapon_instance_id=bow.id,
            action_type=CombatActionType.MELEE_ATTACK,
            damage_profile=PhysicalDamageProfile.PIERCE,
            action_key="wrong-bow-action",
        )

    result = resolve_weapon_attack(
        db_session,
        encounter,
        hero,
        enemy,
        weapon_instance_id=bow.id,
        action_type=CombatActionType.RANGED_ATTACK,
        damage_profile=PhysicalDamageProfile.PIERCE,
        action_key="far-shot",
        rng=SequenceRng(10, 1),
    )
    assert result.action.action_type == CombatActionType.RANGED_ATTACK.value


def test_inventory_api_exposes_weapon_capabilities_without_generic_bonuses(
    client,
    db_session,
):
    campaign = client.post("/api/campaigns", json={"name": "Weapon API"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters",
        json={"name": "Hero"},
    ).json()
    _profile, sword = _weapon(
        db_session,
        character["id"],
        hand_requirement=WeaponHandRequirement.ONE_HAND,
        allowed_slots={EquipmentSlot.MAIN_HAND, EquipmentSlot.WAIST},
    )

    response = client.get(
        f"/api/campaigns/{campaign['id']}/inventory",
        params={"character_id": character["id"]},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["item_instance_id"] == sword.id
    assert item["weapon"] == {
        "family": "SWORD",
        "damage_profiles": ["PIERCE", "SLASH"],
        "reach": "NORMAL",
        "hand_requirement": "ONE_HAND",
    }
    assert "attack_bonus" not in item["weapon"]
    assert "balance" not in item["weapon"]
