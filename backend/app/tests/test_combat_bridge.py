from app.ai.intent_parser import Intent
from app.core.enums import (
    ActionIntentType,
    CombatActorType,
    EquipmentSlot,
    PhysicalDamageProfile,
    WeaponFamily,
    WeaponHandRequirement,
    WeaponReach,
)
from app.db.models.combat import CombatAction, CombatEncounter, CombatParticipant, CombatTacticalAction
from app.db.models.npc import NPC
from app.game import engine
from app.game.character.service import create_character
from app.game.combat.encounters import get_active_encounter_for_actor
from app.game.game_state import build_game_state
from app.game.inventory.service import add_item, get_or_create_item
from app.game.items.equipment import configure_item_equipment_profile, equip_item
from app.game.items.weapons import configure_item_weapon_profile
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session, *, npc_names=("Bandido",), npc_hp=None):
    campaign = create_campaign(db_session, "Combat Bridge")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)

    npcs = []
    for name in npc_names:
        npc = NPC(
            campaign_id=campaign.id,
            region_id=region.id,
            location_id=village.id,
            name=name,
            role="bandit",
            alive=True,
        )
        db_session.add(npc)
        npcs.append(npc)
    db_session.flush()

    if npc_hp is not None:
        for npc in npcs:
            npc.hp_current = npc_hp
            npc.hp_max = npc_hp

    db_session.commit()
    return campaign, region, village, character, npcs


_ATTACK_OUTCOME_WORDS = ("acerta", "erra")


def test_attack_intent_creates_encounter_against_unambiguous_nearby_npc(db_session):
    campaign, _region, _village, character, (bandido,) = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)
    intent = Intent(type=ActionIntentType.ATTACK, target="Bandido", raw_text="Ataco o bandido!")

    summary, minutes = engine._apply_intent(
        db_session, campaign.id, character, intent, state, action_key="attack-1",
    )

    assert minutes == 0
    assert any(word in summary for word in _ATTACK_OUTCOME_WORDS)
    assert (
        db_session.query(CombatEncounter)
        .filter(CombatEncounter.campaign_id == campaign.id)
        .count()
        == 1
    )
    assert db_session.query(CombatAction).count() >= 1
    actor_ids = {row.actor_id for row in db_session.query(CombatParticipant).all()}
    assert bandido.id in actor_ids
    assert character.id in actor_ids


def test_attack_intent_selects_the_named_target_among_several_candidates(db_session):
    campaign, _region, _village, character, (norte, sul) = _setup(
        db_session, npc_names=("Bandido do Norte", "Bandido do Sul"), npc_hp=1000,
    )
    character.hp_current = 1000
    character.hp_max = 1000
    db_session.commit()

    state = build_game_state(db_session, campaign.id, character.id)
    intent = Intent(type=ActionIntentType.ATTACK, target="Sul", raw_text="Ataco o bandido do sul")

    summary, minutes = engine._apply_intent(
        db_session, campaign.id, character, intent, state, action_key="attack-2",
    )

    assert minutes == 0
    assert any(word in summary for word in _ATTACK_OUTCOME_WORDS)
    actor_ids = {
        row.actor_id
        for row in db_session.query(CombatParticipant)
        .filter(CombatParticipant.actor_type == CombatActorType.NPC.value)
        .all()
    }
    assert sul.id in actor_ids
    assert norte.id not in actor_ids


def test_attack_intent_without_target_and_multiple_candidates_is_rejected(db_session):
    campaign, _region, _village, character, _npcs = _setup(
        db_session, npc_names=("Bandido do Norte", "Bandido do Sul"),
    )
    state = build_game_state(db_session, campaign.id, character.id)
    intent = Intent(type=ActionIntentType.ATTACK, target=None, raw_text="Eu ataco!")

    summary, minutes = engine._apply_intent(
        db_session, campaign.id, character, intent, state, action_key="attack-3",
    )

    assert minutes == 0
    assert "indicar um alvo" in summary
    assert db_session.query(CombatEncounter).count() == 0


def test_attack_intent_against_unknown_name_is_rejected_without_creating_encounter(db_session):
    campaign, _region, _village, character, _npcs = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)
    intent = Intent(type=ActionIntentType.ATTACK, target="Dragão", raw_text="Ataco o dragão")

    summary, minutes = engine._apply_intent(
        db_session, campaign.id, character, intent, state, action_key="attack-4",
    )

    assert minutes == 0
    assert "Nenhum alvo" in summary
    assert db_session.query(CombatEncounter).count() == 0


def test_repeated_attack_intent_reuses_the_same_active_encounter(db_session):
    campaign, _region, _village, character, (bandido,) = _setup(
        db_session, npc_names=("Bandido",), npc_hp=1000,
    )
    character.hp_current = 1000
    character.hp_max = 1000
    db_session.commit()

    state = build_game_state(db_session, campaign.id, character.id)
    intent = Intent(type=ActionIntentType.ATTACK, target="Bandido", raw_text="Ataco o bandido")

    summary, minutes = engine._apply_intent(
        db_session, campaign.id, character, intent, state, action_key="attack-5a",
    )
    assert minutes == 0
    assert any(word in summary for word in _ATTACK_OUTCOME_WORDS)
    assert (
        db_session.query(CombatEncounter)
        .filter(CombatEncounter.campaign_id == campaign.id)
        .count()
        == 1
    )
    assert (
        get_active_encounter_for_actor(db_session, CombatActorType.CHARACTER, character.id)
        is not None
    )

    state = build_game_state(db_session, campaign.id, character.id)
    engine._apply_intent(
        db_session, campaign.id, character, intent, state, action_key="attack-5b",
    )

    assert (
        db_session.query(CombatEncounter)
        .filter(CombatEncounter.campaign_id == campaign.id)
        .count()
        == 1
    )


def test_defend_intent_requires_an_active_encounter(db_session):
    campaign, _region, _village, character, _npcs = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)
    intent = Intent(type=ActionIntentType.DEFEND, target=None, raw_text="Eu me defendo.")

    summary, minutes = engine._apply_intent(
        db_session, campaign.id, character, intent, state, action_key="defend-1",
    )

    assert minutes == 0
    assert "não está em combate" in summary


def test_defend_intent_during_active_encounter_resolves_a_guard_action(db_session):
    campaign, _region, _village, character, (bandido,) = _setup(
        db_session, npc_names=("Bandido",), npc_hp=1000,
    )
    character.hp_current = 1000
    character.hp_max = 1000
    db_session.commit()

    state = build_game_state(db_session, campaign.id, character.id)
    attack_intent = Intent(type=ActionIntentType.ATTACK, target="Bandido", raw_text="Ataco")
    engine._apply_intent(
        db_session, campaign.id, character, attack_intent, state, action_key="defend-setup",
    )

    state = build_game_state(db_session, campaign.id, character.id)
    defend_intent = Intent(type=ActionIntentType.DEFEND, target=None, raw_text="Eu me defendo.")
    summary, minutes = engine._apply_intent(
        db_session, campaign.id, character, defend_intent, state, action_key="defend-2",
    )

    assert minutes == 0
    tactical = (
        db_session.query(CombatTacticalAction)
        .filter(CombatTacticalAction.action_type == "GUARD")
        .all()
    )
    assert len(tactical) == 1
    assert tactical[0].actor_participant.actor_id == character.id
    assert "postura defensiva" in summary


def test_attack_intent_uses_named_equipped_weapon(db_session):
    campaign, _region, _village, character, (_bandido,) = _setup(
        db_session, npc_names=("Bandido",), npc_hp=1000,
    )
    definition = get_or_create_item(db_session, "Espada Longa", "weapon")
    configure_item_equipment_profile(
        db_session,
        definition,
        allowed_slots={
            EquipmentSlot.MAIN_HAND,
            EquipmentSlot.BOTH_HANDS,
            EquipmentSlot.WAIST,
        },
    )
    configure_item_weapon_profile(
        db_session,
        definition,
        weapon_family=WeaponFamily.SWORD,
        damage_profiles={PhysicalDamageProfile.SLASH},
        reach=WeaponReach.NORMAL,
        hand_requirement=WeaponHandRequirement.ONE_OR_TWO_HANDS,
    )
    instance = add_item(db_session, character.id, "Espada Longa")
    equip_item(db_session, instance, slot=EquipmentSlot.MAIN_HAND)
    db_session.commit()

    state = build_game_state(db_session, campaign.id, character.id)
    intent = Intent(
        type=ActionIntentType.ATTACK,
        target="Bandido",
        raw_text="Ataco o bandido com a espada longa, cortando o torso",
        weapon="Espada Longa",
        attack_type="MELEE_ATTACK",
        damage_profile="SLASH",
        body_area="TORSO",
    )

    summary, minutes = engine._apply_intent(
        db_session, campaign.id, character, intent, state, action_key="attack-weapon",
    )

    assert minutes == 0
    assert "Espada Longa" in summary
    action = (
        db_session.query(CombatAction)
        .filter(CombatAction.weapon_instance_id == instance.id)
        .one()
    )
    assert action.physical_damage_profile == "SLASH"
    assert action.target_body_area == "TORSO"
