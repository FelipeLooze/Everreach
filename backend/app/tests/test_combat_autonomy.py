import json

import pytest

from app.core.enums import (
    CombatActionType,
    CombatActorType,
    CombatDecisionKind,
    CombatEncounterStatus,
    CombatRangeBand,
    CombatTacticalActionType,
    EventType,
    RiskTolerance,
    SimulatedPlayerArchetype,
    SimulatedPlayerStatus,
)
from app.db.models.combat import (
    CombatAutonomousDecision,
    CombatParticipant,
    CombatTacticalAction,
)
from app.db.models.event import WorldEvent
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.game.character.service import create_character
from app.game.combat.autonomy import (
    CombatAutonomyError,
    _choose_action,
    resolve_autonomous_turn,
    resolve_until_player_turn,
)
from app.game.combat.encounters import CombatantSpec, add_participant, start_encounter
from app.game.combat.turns import get_current_turn, roll_initiative
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign, seed_initial_region


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


class ExplodingRng:
    def randint(self, _minimum: int, _maximum: int) -> int:
        raise AssertionError("A replay must not roll again.")


@pytest.mark.parametrize(
    ("risk", "hp_ratio", "expected"),
    [
        (RiskTolerance.CAUTIOUS.value, 0.50, CombatTacticalActionType.FLEE),
        (RiskTolerance.BALANCED.value, 0.30, CombatTacticalActionType.FLEE),
        (RiskTolerance.BOLD.value, 0.15, CombatTacticalActionType.FLEE),
        (RiskTolerance.BOLD.value, 0.16, CombatTacticalActionType.APPROACH),
    ],
)
def test_risk_tolerance_changes_the_flee_threshold(risk, hp_ratio, expected):
    target = CombatParticipant(range_band=CombatRangeBand.NEAR.value)

    choice = _choose_action(
        target,
        hp_ratio=hp_ratio,
        stamina=20,
        risk_tolerance=risk,
    )

    assert choice.action_type == expected


def _setup_npc(db_session, *, hero_range=CombatRangeBand.ENGAGED):
    campaign = create_campaign(db_session, "Combat Autonomy")
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
        name="Bandido",
        role="bandit",
        alive=True,
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
                range_band=hero_range,
            ),
            CombatantSpec(CombatActorType.NPC, enemy.id, "bandits"),
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
        region,
        location,
        character,
        enemy,
        encounter,
        participants[character.id],
        participants[enemy.id],
    )


def test_npc_autonomy_attacks_engaged_target_and_replay_is_idempotent(db_session):
    campaign, _region, _location, character, enemy, encounter, hero, bandit = (
        _setup_npc(db_session)
    )
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))

    first = resolve_autonomous_turn(
        db_session,
        encounter,
        decision_key="npc-turn-1",
        rng=SequenceRng(10, 2),
    )
    hp_after = character.hp_current
    stamina_after = enemy.stamina_current
    replay = resolve_autonomous_turn(
        db_session,
        encounter,
        decision_key="npc-turn-1",
        rng=ExplodingRng(),
    )

    assert first.decision.decision_kind == CombatDecisionKind.ATTACK.value
    assert first.decision.action_type == CombatActionType.MELEE_ATTACK.value
    assert first.decision.reason == "ENGAGED_ATTACK"
    assert first.decision.risk_tolerance == RiskTolerance.BALANCED.value
    assert first.decision.target_participant_id == hero.id
    assert first.combat_action is not None
    assert first.combat_action.actor_participant_id == bandit.id
    assert get_current_turn(db_session, encounter).participant_id == hero.id
    assert replay.replayed is True
    assert replay.decision.id == first.decision.id
    assert character.hp_current == hp_after
    assert enemy.stamina_current == stamina_after == 8
    assert db_session.query(CombatAutonomousDecision).count() == 1
    event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.event_type
            == EventType.COMBAT_AUTONOMOUS_DECISION_RESOLVED.value
        )
        .one()
    )
    payload = json.loads(event.payload_json)
    assert payload["combat_action_id"] == first.combat_action.id
    assert event.campaign_id == campaign.id


def test_autonomy_approaches_when_opponent_is_out_of_reach(db_session):
    (
        _campaign,
        _region,
        _location,
        _character,
        enemy,
        encounter,
        hero,
        bandit,
    ) = _setup_npc(db_session, hero_range=CombatRangeBand.OUT_OF_REACH)
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))

    result = resolve_autonomous_turn(
        db_session,
        encounter,
        decision_key="npc-approach",
    )

    assert result.decision.decision_kind == CombatDecisionKind.TACTICAL.value
    assert result.decision.action_type == CombatTacticalActionType.APPROACH.value
    assert result.decision.reason == "TARGET_OUT_OF_REACH"
    assert result.tactical_action.target_participant_id == hero.id
    assert hero.range_band == CombatRangeBand.FAR.value
    assert enemy.stamina_current == 9
    assert get_current_turn(db_session, encounter).participant_id != bandit.id


def test_autonomy_uses_ranged_attack_only_with_real_capability(db_session):
    (
        _campaign,
        _region,
        _location,
        _character,
        enemy,
        encounter,
        hero,
        _bandit,
    ) = _setup_npc(db_session, hero_range=CombatRangeBand.NEAR)
    enemy.role = "archer"
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))

    result = resolve_autonomous_turn(
        db_session,
        encounter,
        decision_key="archer-shot",
        rng=SequenceRng(10, 1),
    )

    assert result.decision.action_type == CombatActionType.RANGED_ATTACK.value
    assert result.decision.reason == "RANGED_OPPORTUNITY"
    assert result.decision.target_participant_id == hero.id


def test_exhausted_autonomous_actor_waits_without_spending_resource(db_session):
    (
        _campaign,
        _region,
        _location,
        _character,
        enemy,
        encounter,
        hero,
        bandit,
    ) = _setup_npc(db_session)
    enemy.stamina_current = 0
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))

    result = resolve_autonomous_turn(
        db_session,
        encounter,
        decision_key="npc-waits",
    )

    assert result.decision.action_type == CombatTacticalActionType.WAIT.value
    assert result.decision.reason == "EXHAUSTED"
    assert result.tactical_action.resource_key is None
    assert result.tactical_action.resource_cost is None
    assert enemy.stamina_current == 0
    assert get_current_turn(db_session, encounter).participant_id == hero.id
    assert db_session.query(CombatTacticalAction).count() == 1


def test_cautious_transported_player_flees_at_half_health(db_session):
    campaign = create_campaign(db_session, "Cautious Autonomy")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    transported = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Mira",
        location_id=location.id,
        archetype=SimulatedPlayerArchetype.EXPLORER.value,
        risk_tolerance=RiskTolerance.CAUTIOUS.value,
        status=SimulatedPlayerStatus.ACTIVE.value,
        hp_current=10,
        hp_max=20,
    )
    db_session.add(transported)
    db_session.flush()
    encounter = start_encounter(
        db_session,
        campaign.id,
        location.id,
        (
            CombatantSpec(CombatActorType.CHARACTER, character.id, "heroes"),
            CombatantSpec(
                CombatActorType.SIMULATED_PLAYER,
                transported.id,
                "rivals",
            ),
        ),
    )
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))

    result = resolve_autonomous_turn(
        db_session,
        encounter,
        decision_key="mira-flees",
        rng=SequenceRng(20),
    )

    assert result.decision.risk_tolerance == RiskTolerance.CAUTIOUS.value
    assert result.decision.hp_ratio == 0.5
    assert result.decision.action_type == CombatTacticalActionType.FLEE.value
    assert result.decision.reason == "LOW_HEALTH_FLEE"
    assert result.tactical_action.success is True
    assert transported.stamina_current == 18
    assert encounter.status == CombatEncounterStatus.VICTORY.value


def test_autonomy_never_decides_for_protagonist(db_session):
    (
        _campaign,
        _region,
        _location,
        _character,
        _enemy,
        encounter,
        _hero,
        _bandit,
    ) = _setup_npc(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))

    with pytest.raises(CombatAutonomyError, match="player decision"):
        resolve_autonomous_turn(
            db_session,
            encounter,
            decision_key="never-control-player",
        )
    assert db_session.query(CombatAutonomousDecision).count() == 0


def test_autonomous_sequence_stops_before_protagonist_turn(db_session):
    campaign, region, location, character, enemy, encounter, hero, _bandit = (
        _setup_npc(db_session)
    )
    transported = SimulatedPlayer(
        campaign_id=campaign.id,
        name="Mira",
        location_id=location.id,
        archetype=SimulatedPlayerArchetype.ADVENTURER.value,
        risk_tolerance=RiskTolerance.BOLD.value,
        status=SimulatedPlayerStatus.ACTIVE.value,
    )
    db_session.add(transported)
    db_session.flush()
    add_participant(
        db_session,
        encounter,
        CombatantSpec(
            CombatActorType.SIMULATED_PLAYER,
            transported.id,
            "bandits",
        ),
    )
    hero.range_band = CombatRangeBand.ENGAGED.value
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20, 19))

    results = resolve_until_player_turn(
        db_session,
        encounter,
        decision_key_prefix="enemy-wave",
        rng=SequenceRng(10, 1, 10, 1),
    )

    assert len(results) == 2
    assert {row.decision.actor_participant_id for row in results} == {
        row.id
        for row in db_session.query(CombatParticipant)
        .filter(
            CombatParticipant.actor_id.in_((enemy.id, transported.id)),
        )
        .all()
    }
    assert get_current_turn(db_session, encounter).participant_id == hero.id


def test_campaign_reset_removes_autonomous_decision_history(db_session):
    (
        campaign,
        _region,
        _location,
        _character,
        _enemy,
        encounter,
        _hero,
        _bandit,
    ) = _setup_npc(db_session)
    roll_initiative(db_session, encounter, rng=SequenceRng(1, 20))
    resolve_autonomous_turn(
        db_session,
        encounter,
        decision_key="before-reset",
        rng=SequenceRng(10, 2),
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(CombatAutonomousDecision).count() == 0
