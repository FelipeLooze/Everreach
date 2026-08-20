import json

import pytest

from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.core.enums import (
    ActionIntentType,
    CharacterStatus,
    CombatActorType,
    EventType,
    RecoveryType,
)
from app.db.models.combat import CombatParticipant
from app.db.models.event import WorldEvent
from app.db.models.npc import NPC
from app.db.models.recovery import CharacterRecovery
from app.game import engine
from app.game.character.service import create_character
from app.game.combat.encounters import CombatantSpec, start_encounter
from app.game.combat.recovery import (
    CombatRecoveryError,
    SHORT_REST_MINUTES,
    recover_character,
)
from app.game.time.clock import get_world_time
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign, seed_initial_region


class PassiveLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return "O descanso transcorre conforme determinado pelo sistema."


def _setup(db_session):
    campaign = create_campaign(db_session, "Combat Recovery")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    return campaign, region, location, character


def test_short_rest_recovers_scaled_resources_and_persists_snapshots(db_session):
    campaign, _region, _location, character = _setup(db_session)
    character.hp_current = 7
    character.mana_current = 1
    character.stamina_current = 3
    character.hp_max = 24
    character.mana_max = 12
    character.stamina_max = 30

    result = recover_character(
        db_session,
        campaign.id,
        character,
        recovery_key="rest-001",
    )

    assert result.replayed is False
    assert result.recovery.recovery_type == RecoveryType.SHORT_REST.value
    assert result.recovery.duration_minutes == SHORT_REST_MINUTES
    assert (character.hp_current, character.mana_current, character.stamina_current) == (
        13,
        4,
        18,
    )
    assert (result.recovery.hp_before, result.recovery.hp_after) == (7, 13)
    assert (result.recovery.mana_before, result.recovery.mana_after) == (1, 4)
    assert (result.recovery.stamina_before, result.recovery.stamina_after) == (3, 18)
    assert "HP +6" in result.mechanical_summary
    event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.PLAYER_RESTED.value)
        .one()
    )
    payload = json.loads(event.payload_json)
    assert payload["recovery_id"] == result.recovery.id
    assert payload["mana"] == {"before": 1.0, "after": 4.0}


def test_short_rest_caps_resources_and_replay_changes_nothing(db_session):
    campaign, _region, _location, character = _setup(db_session)
    character.hp_current = 19
    character.mana_current = 9
    character.stamina_current = 19

    first = recover_character(
        db_session,
        campaign.id,
        character,
        recovery_key="same-rest",
    )
    first_values = (
        character.hp_current,
        character.mana_current,
        character.stamina_current,
    )
    replay = recover_character(
        db_session,
        campaign.id,
        character,
        recovery_key="same-rest",
    )

    assert first_values == (20, 10, 20)
    assert replay.replayed is True
    assert replay.recovery.id == first.recovery.id
    assert db_session.query(CharacterRecovery).count() == 1
    assert (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.PLAYER_RESTED.value)
        .count()
        == 1
    )


def test_recovery_rejects_dead_character_and_active_combat(db_session):
    campaign, region, location, character = _setup(db_session)
    character.status = CharacterStatus.DEAD.value
    character.hp_current = 0
    with pytest.raises(CombatRecoveryError, match="Dead characters"):
        recover_character(
            db_session,
            campaign.id,
            character,
            recovery_key="dead-rest",
        )

    character.status = CharacterStatus.ALIVE.value
    character.hp_current = 10
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
    start_encounter(
        db_session,
        campaign.id,
        location.id,
        (
            CombatantSpec(CombatActorType.CHARACTER, character.id, "heroes"),
            CombatantSpec(CombatActorType.NPC, enemy.id, "bandits"),
        ),
    )

    with pytest.raises(CombatRecoveryError, match="active combat"):
        recover_character(
            db_session,
            campaign.id,
            character,
            recovery_key="combat-rest",
        )
    assert db_session.query(CharacterRecovery).count() == 0
    assert db_session.query(CombatParticipant).count() == 2


def test_rest_intent_retry_does_not_recover_or_advance_time_twice(
    db_session,
    monkeypatch,
):
    campaign, _region, _location, character = _setup(db_session)
    character.hp_current = 10
    character.mana_current = 0
    character.stamina_current = 0
    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *_args, **_kwargs: Intent(
            type=ActionIntentType.REST,
            target=None,
            raw_text="Eu descanso.",
        ),
    )
    started_at = get_world_time(db_session, campaign.id).total_minutes()

    first = engine.resolve_action(
        db_session,
        PassiveLLM(),
        campaign.id,
        character.id,
        "Eu descanso.",
        action_key="rest-http-001",
    )
    second = engine.resolve_action(
        db_session,
        PassiveLLM(),
        campaign.id,
        character.id,
        "Eu descanso.",
        action_key="rest-http-001",
    )

    assert first.mechanical_summary == second.mechanical_summary
    assert (character.hp_current, character.mana_current, character.stamina_current) == (
        15,
        2.5,
        10,
    )
    assert (
        get_world_time(db_session, campaign.id).total_minutes() - started_at
        == SHORT_REST_MINUTES
    )
    assert db_session.query(CharacterRecovery).count() == 1


def test_campaign_reset_removes_recovery_history(db_session):
    campaign, _region, _location, character = _setup(db_session)
    recover_character(
        db_session,
        campaign.id,
        character,
        recovery_key="before-reset",
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(CharacterRecovery).count() == 0
