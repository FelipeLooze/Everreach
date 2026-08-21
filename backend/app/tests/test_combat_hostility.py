import random

from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.api.serializers import to_game_state_response
from app.core.enums import ActionIntentType, CombatActorType, CombatEncounterStatus
from app.db.models.combat import CombatEncounter
from app.db.models.npc import NPC
from app.game import engine
from app.game.character.service import create_character
from app.game.combat import bridge as combat_bridge
from app.game.combat import hostility as combat_hostility
from app.game.combat.encounters import get_active_encounter_for_actor
from app.game.game_state import build_game_state
from app.game.world.seed import create_campaign, seed_initial_region


class ForcedTriggerRng:
    """Always wins probability checks (`.random()` returns 0.0); delegates
    dice rolls (`.randint()`) to a real RNG so combat resolution itself
    stays realistic."""

    def __init__(self, seed: int = 0) -> None:
        self._real = random.Random(seed)

    def random(self) -> float:
        return 0.0

    def randint(self, a: int, b: int) -> int:
        return self._real.randint(a, b)


def _hostile_scene(db_session, *, hostility: int = 100):
    campaign = create_campaign(db_session, "Hostility")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    character.region_id = region.id
    character.location_id = village.id
    npc = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=village.id,
        name="Bandido",
        role="bandit",
        alive=True,
        hostility=hostility,
    )
    db_session.add(npc)
    db_session.flush()
    db_session.commit()
    return campaign, character, npc


def test_attacking_an_npc_marks_it_hostile(db_session):
    campaign, character, npc = _hostile_scene(db_session, hostility=0)
    state = build_game_state(db_session, campaign.id, character.id)
    intent = Intent(type=ActionIntentType.ATTACK, target="Bandido", raw_text="Ataco o bandido")

    combat_bridge.handle_attack_intent(
        db_session, campaign.id, character, intent, state, action_key="hostility-1",
    )

    db_session.refresh(npc)
    assert npc.hostility == 100


def test_resolve_ambush_starts_an_encounter_when_hostile_npc_present(db_session):
    campaign, character, npc = _hostile_scene(db_session, hostility=100)

    ambush = combat_hostility.resolve_ambush_for_character(
        db_session, campaign.id, character, rng=ForcedTriggerRng(),
    )

    assert ambush is not None
    assert ambush.npc_id == npc.id
    assert ambush.character_id == character.id

    encounter = db_session.get(CombatEncounter, ambush.encounter_id)
    assert encounter is not None
    assert encounter.status == CombatEncounterStatus.ACTIVE.value
    assert (
        get_active_encounter_for_actor(db_session, CombatActorType.CHARACTER, character.id)
        is not None
    )


def test_resolve_ambush_does_not_trigger_below_hostility_threshold(db_session):
    campaign, character, _npc = _hostile_scene(db_session, hostility=10)

    ambush = combat_hostility.resolve_ambush_for_character(
        db_session, campaign.id, character, rng=ForcedTriggerRng(),
    )

    assert ambush is None
    assert (
        get_active_encounter_for_actor(db_session, CombatActorType.CHARACTER, character.id)
        is None
    )


def test_resolve_ambush_skips_a_character_already_in_combat(db_session):
    campaign, character, npc = _hostile_scene(db_session, hostility=100)
    state = build_game_state(db_session, campaign.id, character.id)
    intent = Intent(type=ActionIntentType.ATTACK, target="Bandido", raw_text="Ataco")
    combat_bridge.handle_attack_intent(
        db_session, campaign.id, character, intent, state, action_key="already-fighting",
    )

    ambush = combat_hostility.resolve_ambush_for_character(
        db_session, campaign.id, character, rng=ForcedTriggerRng(),
    )

    assert ambush is None
    assert (
        db_session.query(CombatEncounter)
        .filter(CombatEncounter.campaign_id == campaign.id)
        .count()
        == 1
    )


class NarratingLLM(LLMService):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if "intent" in system.lower():
            return '{"intent": "WAIT", "target": null}'
        return "O tempo passa devagar."


def test_engine_appends_ambush_narration_and_updates_game_state(db_session, monkeypatch):
    campaign, character, npc = _hostile_scene(db_session, hostility=100)

    real_resolve = combat_hostility.resolve_ambush_for_character

    def forced_resolve(db, campaign_id, character_arg, **kwargs):
        return real_resolve(db, campaign_id, character_arg, rng=ForcedTriggerRng())

    monkeypatch.setattr(engine.combat_hostility, "resolve_ambush_for_character", forced_resolve)

    llm = NarratingLLM()
    result = engine.resolve_action(
        db_session, llm, campaign.id, character.id, "Eu espero.",
    )

    assert npc.name in result.mechanical_summary
    assert "combate" in result.mechanical_summary.lower()

    state_after = build_game_state(db_session, campaign.id, character.id)
    response_after = to_game_state_response(db_session, state_after)
    assert response_after.active_encounter is not None
    assert response_after.active_encounter.status == "ACTIVE"
    names = {p.name for p in response_after.active_encounter.participants}
    assert "Bandido" in names
    assert character.name in names
