import pytest

from app.core.enums import (
    CharacterStatus,
    CombatActionType,
    CombatActorType,
    CombatIncapacitationStatus,
    CombatRangeBand,
    EventType,
)
from app.db.models.combat import CombatCriticalCheck, CombatIncapacitation, CombatParticipant
from app.db.models.event import WorldEvent
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.combat.actions import resolve_attack
from app.game.combat.encounters import CombatantSpec, start_encounter
from app.game.combat.incapacitation import (
    CombatIncapacitationError,
    recover_stabilized_actor,
    resolve_critical_check,
)
from app.game.combat.turns import roll_initiative
from app.game.world.seed import create_campaign, seed_initial_region


class SequenceRng:
    def __init__(self, *values):
        self.values = iter(values)

    def randint(self, _minimum, _maximum):
        return next(self.values)


def _incapacitated_character(db):
    campaign = create_campaign(db, "Critical State")
    region, location = seed_initial_region(db, campaign.id)
    character = create_character(db, campaign.id, "Hero", region.id, location.id)
    character.hp_current = 1
    npc = NPC(campaign_id=campaign.id, region_id=region.id, location_id=location.id, name="Bandit")
    db.add(npc)
    db.flush()
    encounter = start_encounter(db, campaign.id, location.id, (
        CombatantSpec(CombatActorType.CHARACTER, character.id, "heroes", range_band=CombatRangeBand.ENGAGED),
        CombatantSpec(CombatActorType.NPC, npc.id, "enemies", range_band=CombatRangeBand.ENGAGED),
    ))
    participants = {p.actor_id: p for p in db.query(CombatParticipant).filter_by(encounter_id=encounter.id).all()}
    roll_initiative(db, encounter, rng=SequenceRng(1, 20))
    action = resolve_attack(db, encounter, participants[npc.id], participants[character.id],
                            action_type=CombatActionType.MELEE_ATTACK, action_key="knockout",
                            rng=SequenceRng(10, 2)).action
    state = db.query(CombatIncapacitation).filter_by(source_action_id=action.id).one()
    return campaign, character, state


def test_three_successes_stabilize_and_checks_are_idempotent(db_session):
    _campaign, character, state = _incapacitated_character(db_session)

    first = resolve_critical_check(db_session, state, check_key="check-1", rng=SequenceRng(10))
    repeated = resolve_critical_check(db_session, state, check_key="check-1", rng=SequenceRng(1))
    resolve_critical_check(db_session, state, check_key="check-2", rng=SequenceRng(10))
    resolve_critical_check(db_session, state, check_key="check-3", rng=SequenceRng(10))

    assert repeated.check.id == first.check.id
    assert db_session.query(CombatCriticalCheck).count() == 3
    assert state.status == CombatIncapacitationStatus.STABILIZED.value
    assert state.stabilization_successes == 3
    assert character.status == CharacterStatus.INCAPACITATED.value


def test_stabilized_actor_recovers_with_one_hp_but_not_into_old_combat(db_session):
    _campaign, character, state = _incapacitated_character(db_session)
    resolve_critical_check(db_session, state, check_key="natural-20", rng=SequenceRng(20))

    recovered = recover_stabilized_actor(db_session, state, recovery_key="aid-1")
    repeated = recover_stabilized_actor(db_session, state, recovery_key="aid-1")

    assert recovered.id == repeated.id
    assert state.status == CombatIncapacitationStatus.RECOVERED.value
    assert character.status == CharacterStatus.ALIVE.value
    assert character.hp_current == 1
    assert state.participant.active is False
    with pytest.raises(CombatIncapacitationError):
        recover_stabilized_actor(db_session, state, recovery_key="aid-2")


def test_critical_failures_cause_permanent_death(db_session):
    campaign, character, state = _incapacitated_character(db_session)
    resolve_critical_check(db_session, state, check_key="failure-1", rng=SequenceRng(1))
    resolve_critical_check(db_session, state, check_key="failure-2", rng=SequenceRng(2))

    assert state.death_failures >= 3
    assert state.status == CombatIncapacitationStatus.DEAD.value
    assert character.status == CharacterStatus.DEAD.value
    assert db_session.query(WorldEvent).filter_by(
        campaign_id=campaign.id, event_type=EventType.PLAYER_DIED.value
    ).count() == 1


def test_devastating_damage_bypasses_critical_state(db_session):
    campaign = create_campaign(db_session, "Devastating Damage")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    character.hp_current = character.hp_max = 1
    npc = NPC(campaign_id=campaign.id, region_id=region.id, location_id=location.id, name="Ogre")
    db_session.add(npc)
    db_session.flush()
    encounter = start_encounter(db_session, campaign.id, location.id, (
        CombatantSpec(CombatActorType.CHARACTER, character.id, "heroes", range_band=CombatRangeBand.ENGAGED),
        CombatantSpec(CombatActorType.NPC, npc.id, "enemies", range_band=CombatRangeBand.ENGAGED),
    ))
    parts = {p.actor_id: p for p in db_session.query(CombatParticipant).filter_by(encounter_id=encounter.id).all()}
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))
    action = resolve_attack(db_session, encounter, parts[npc.id], parts[character.id],
                            action_type=CombatActionType.MELEE_ATTACK, action_key="devastating",
                            rng=SequenceRng(10, 2)).action

    assert action.lethal is True
    assert action.incapacitating is False
    assert character.status == CharacterStatus.DEAD.value
    assert db_session.query(CombatIncapacitation).count() == 0
