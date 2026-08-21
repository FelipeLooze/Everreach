import pytest

from app.core.enums import (
    CharacterAttributeKey,
    CharacterResourceKey,
    CombatActionType,
    CombatActorType,
    CombatDamageType,
    CombatRangeBand,
    EquipmentSlot,
    PhysicalDamageProfile,
    TechniqueOrigin,
    TechniqueType,
    WeaponFamily,
    WeaponHandRequirement,
    WeaponReach,
)
from app.db.models.combat import CombatParticipant
from app.db.models.domain import DomainDefinition
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.combat.encounters import CombatantSpec, start_encounter
from app.game.combat.techniques import (
    CombatTechniqueError,
    configure_combat_technique,
    resolve_combat_technique,
)
from app.game.combat.turns import roll_initiative
from app.game.inventory.service import add_item, get_or_create_item
from app.game.items.equipment import configure_item_equipment_profile, equip_item
from app.game.items.weapons import configure_item_weapon_profile
from app.game.skills.techniques import create_technique, grant_technique
from app.game.world.seed import create_campaign, seed_initial_region


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


def _weapon(
    db_session,
    character_id,
    *,
    name="Espada Longa",
    family=WeaponFamily.SWORD,
    reach=WeaponReach.NORMAL,
    active_slot=EquipmentSlot.MAIN_HAND,
):
    definition = get_or_create_item(db_session, name, "weapon")
    configure_item_equipment_profile(
        db_session,
        definition,
        allowed_slots={EquipmentSlot.MAIN_HAND, EquipmentSlot.BOTH_HANDS, EquipmentSlot.WAIST},
    )
    configure_item_weapon_profile(
        db_session,
        definition,
        weapon_family=family,
        damage_profiles={PhysicalDamageProfile.SLASH, PhysicalDamageProfile.PIERCE},
        reach=reach,
        hand_requirement=WeaponHandRequirement.ONE_OR_TWO_HANDS,
    )
    instance = add_item(db_session, character_id, name)
    equip_item(db_session, instance, slot=active_slot)
    return instance


def _setup(db_session, *, required_weapon_family=WeaponFamily.SWORD):
    if db_session.get(DomainDefinition, "SWORD") is None:
        db_session.add(DomainDefinition(key="SWORD", family="WEAPON", description=""))
    campaign = create_campaign(db_session, "Technique Weapon Requirement")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    enemy = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Alvo",
        role="alvo de treino",
        hp_current=30,
        hp_max=30,
    )
    db_session.add(enemy)
    technique = create_technique(
        db_session,
        skill_name="Esgrima",
        name="Estocada Avançada",
        technique_type=TechniqueType.PHYSICAL,
        domain_keys=("SWORD",),
    )
    grant_technique(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.SELF_DISCOVERED
    )
    configure_combat_technique(
        db_session,
        technique,
        action_type=CombatActionType.MELEE_ATTACK,
        attack_attribute=CharacterAttributeKey.STRENGTH,
        resource_key=CharacterResourceKey.STAMINA,
        resource_cost=3,
        base_damage_dice=2,
        damage_die_sides=6,
        damage_attribute=CharacterAttributeKey.STRENGTH,
        damage_type=CombatDamageType.PHYSICAL,
        required_weapon_family=required_weapon_family,
    )
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
                "enemies",
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
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    return campaign, character, technique, encounter, participants[character.id], participants[enemy.id]


def test_technique_without_weapon_requirement_is_unaffected(db_session):
    campaign, character, technique, encounter, hero, enemy = _setup(
        db_session, required_weapon_family=None
    )

    result = resolve_combat_technique(
        db_session,
        encounter,
        hero,
        enemy,
        technique_id=technique.id,
        action_key="unarmed-use",
        rng=SequenceRng(10, 4, 5),
    )

    assert result.action.weapon_instance_id is None


def test_technique_rejects_use_without_the_required_weapon_equipped(db_session):
    campaign, character, technique, encounter, hero, enemy = _setup(db_session)

    with pytest.raises(CombatTechniqueError, match="No Sword is equipped"):
        resolve_combat_technique(
            db_session,
            encounter,
            hero,
            enemy,
            technique_id=technique.id,
            action_key="no-weapon-use",
            rng=SequenceRng(10, 4),
        )


def test_technique_rejects_the_wrong_weapon_family(db_session):
    campaign, character, technique, encounter, hero, enemy = _setup(db_session)
    _weapon(db_session, character.id, name="Adaga", family=WeaponFamily.DAGGER)

    with pytest.raises(CombatTechniqueError, match="No Sword is equipped"):
        resolve_combat_technique(
            db_session,
            encounter,
            hero,
            enemy,
            technique_id=technique.id,
            action_key="wrong-weapon-use",
            rng=SequenceRng(10, 4),
        )


def test_technique_succeeds_and_references_the_weapon_when_correctly_equipped(db_session):
    campaign, character, technique, encounter, hero, enemy = _setup(db_session)
    weapon = _weapon(db_session, character.id)

    result = resolve_combat_technique(
        db_session,
        encounter,
        hero,
        enemy,
        technique_id=technique.id,
        action_key="correct-weapon-use",
        rng=SequenceRng(10, 4, 5),
    )

    assert result.action.weapon_instance_id == weapon.id
    assert result.action.technique_id == technique.id


def test_technique_rejects_a_ranged_only_weapon_for_a_melee_technique(db_session):
    campaign, character, technique, encounter, hero, enemy = _setup(
        db_session, required_weapon_family=WeaponFamily.BOW
    )
    _weapon(
        db_session,
        character.id,
        name="Arco Curto",
        family=WeaponFamily.BOW,
        reach=WeaponReach.RANGED,
    )

    with pytest.raises(CombatTechniqueError, match="does not support this attack type"):
        resolve_combat_technique(
            db_session,
            encounter,
            hero,
            enemy,
            technique_id=technique.id,
            action_key="reach-mismatch-use",
            rng=SequenceRng(10, 4),
        )
