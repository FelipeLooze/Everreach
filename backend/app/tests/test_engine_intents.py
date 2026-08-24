import json
from app.db.models.event import WorldEvent
from app.game.time.clock import get_world_time
from app.game.travel import service as travel_service
from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.core.enums import (
    ActionIntentType,
    DiscoveryStatus,
    MemoryOwnerType,
    ObjectiveTriggerType,
    TravelPace,
)
from app.core.enums import EventType
from app.db.models.npc import NPC
from app.db.models.location import Location, LocationConnection
from app.db.models.quest import CharacterQuestObjective
from app.db.models.memory import Memory
from app.db.models.relationship import CharacterNPCRelationship
from app.game import engine
from app.game import dice
from app.game.combat import service as combat_service
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.quests.service import start_quest
from app.game.world.seed import create_campaign, seed_initial_region
from app.db.models.quest import Quest, QuestObjective
from app.game.npcs import service as npcs_service
from app.services.event_log import log_event
from app.game.discovery.service import (
    discover_connection,
    get_connection_discovery,
    get_location_discovery,
    set_location_discovery,
)
from app.core.enums import NPCActivity
from app.game.time import clock

def _setup(db_session):
    campaign = create_campaign(db_session, "Intent Test")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.commit()
    return campaign, region, village, character


def test_apply_intent_move_relocates_character(db_session):
    campaign, region, village, character = _setup(db_session)
    forest = db_session.query(Location).filter(Location.subregion_id == village.subregion_id, Location.type == "forest").first()
    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == forest.id,
        )
        .one()
    )

    connection.danger = 0

    discover_connection(
        db_session,
        character.id,
        connection.id,
    )

    set_location_discovery(
        db_session,
        character.id,
        forest.id,
        DiscoveryStatus.DISCOVERED,
    )
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.MOVE, target=forest.name, raw_text="I walk to the forest")
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert minutes > 0
    assert forest.name in summary
    assert character.location_id != village.id

    discovery = get_location_discovery(
        db_session,
        character.id,
        forest.id,
    )

    assert discovery is not None
    assert discovery.status == DiscoveryStatus.VISITED
    assert forest.discovery_status == DiscoveryStatus.UNKNOWN


def test_apply_intent_move_does_not_reveal_unknown_location(db_session):
    campaign, region, village, character = _setup(db_session)
    forest = db_session.query(Location).filter(Location.subregion_id == village.subregion_id, Location.type == "forest").first()
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.MOVE, target=forest.name, raw_text="Vou ao bosque")
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert minutes == 0
    assert "Nenhum lugar conhecido" in summary
    assert character.location_id == village.id


def test_apply_intent_talk_resolves_npc_by_role_when_target_is_not_a_name(db_session):
    campaign, region, village, character = _setup(db_session)
    innkeeper = db_session.query(NPC).filter(NPC.role == "estalajadeiro").first()
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.TALK, target="estalajadeiro", raw_text="Eu falo com o estalajadeiro")
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert innkeeper.name in summary
    assert minutes >= 0


def test_apply_intent_talk_ignores_llm_target_not_present_in_player_text(db_session):
    # Regression: the Intent Parser LLM can infer a plausible-looking
    # `target` (e.g. a nearby NPC's role) from broader scene context even
    # when the player named no one — this must never be trusted for who
    # gets talked to. Reproduces a real bug report: the starting village
    # seeds an "ancião da vila" and an "estalajadeiro" at the SAME
    # location, the player greeted "senhor" with no name, and the wrong
    # NPC ended up as the interlocutor because the engine trusted an
    # LLM-guessed target the player never actually wrote.
    campaign, region, village, character = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(
        type=ActionIntentType.TALK,
        target="estalajadeiro",
        raw_text='"Olá, bom dia, senhor. Como está?"',
    )
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert "Há mais de uma pessoa aqui" in summary
    assert minutes == 0


def test_apply_intent_talk_reports_ambiguity_with_multiple_nearby_and_no_target(db_session):
    campaign, region, village, character = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.TALK, target=None, raw_text='"Bom dia!"')
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert "Há mais de uma pessoa aqui" in summary
    assert minutes == 0


def test_apply_intent_talk_completes_matching_quest_objective(db_session):
    campaign, region, village, character = _setup(db_session)

    osgar = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()

    quest = Quest(
        region_id=region.id,
        name="Falar com o Ancião",
        description="Quest criada exclusivamente para testar objetivos de conversa.",
    )
    db_session.add(quest)
    db_session.flush()

    objective = QuestObjective(
        quest_id=quest.id,
        description=f"Falar com {osgar.name} em {village.name}.",
        order=0,
        trigger_type=ObjectiveTriggerType.TALK_TO_NPC,
        trigger_subject_id=osgar.id,
    )
    db_session.add(objective)
    db_session.flush()

    start_quest(db_session, character.id, quest.id)


    db_session.commit()

    state = build_game_state(db_session, campaign.id, character.id)
    intent = Intent(type=ActionIntentType.TALK, target=osgar.name, raw_text=f"I talk to {osgar.name}")
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert osgar.name in summary
    assert minutes == 0

    world_time = clock.get_world_time(
        db_session,
        campaign.id,
    )

    assert world_time.subminute_seconds == 2

    completed = (
        db_session.query(CharacterQuestObjective)
        .filter(CharacterQuestObjective.character_id == character.id, CharacterQuestObjective.completed.is_(True))
        .all()
    )
    assert len(completed) == 1


def test_apply_intent_skill_check_produces_dice_backed_result(db_session):
    campaign, region, village, character = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.SKILL_CHECK, target="Atletismo", raw_text="I try to leap the fence")
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert "Atletismo" in summary
    assert ("tem sucesso" in summary) or ("falha" in summary)
    assert minutes > 0


def test_successful_skill_check_does_not_automatically_award_character_xp(
    db_session,
    monkeypatch,
):
    campaign, _region, _village, character = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)
    result = combat_service.SkillCheckResult(
        skill_name="Atletismo",
        dc=12,
        roll=dice.RollResult(sides=20, raw=20, modifier=0),
        success=True,
        critical=True,
    )
    monkeypatch.setattr(combat_service, "resolve_skill_check", lambda *_args, **_kwargs: result)

    intent = Intent(
        type=ActionIntentType.SKILL_CHECK,
        target="Atletismo",
        raw_text="Repito a mesma ação fácil.",
    )
    engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert character.xp == 0
    assert (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type == EventType.PLAYER_GAINED_XP.value,
            WorldEvent.actor_id == character.id,
        )
        .count()
        == 0
    )


def test_apply_intent_move_rejects_unreachable_target(db_session):
    campaign, region, village, character = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.MOVE, target="Nonexistent Place", raw_text="I walk to nowhere")
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert minutes == 0
    assert character.location_id == village.id


def test_active_interlocutor_comes_from_events_and_scene_boundaries_clear_it(db_session):
    campaign, _region, village, character = _setup(db_session)
    npc = db_session.query(NPC).filter(NPC.location_id == village.id).first()

    npcs_service.meet_npc(db_session, campaign.id, character.id, npc.id)
    assert npcs_service.get_active_interlocutor(
        db_session, campaign.id, character.id, village.id
    ).id == npc.id

    log_event(
        db_session,
        campaign.id,
        EventType.PLAYER_RESTED,
        actor_type="character",
        actor_id=character.id,
    )
    assert npcs_service.get_active_interlocutor(
        db_session, campaign.id, character.id, village.id
    ) is None


class ConversationLLM(LLMService):
    def __init__(self, elder_first_name: str, elder_full_name: str) -> None:
        self.calls: list[tuple[str, str]] = []
        self.elder_first_name = elder_first_name
        self.elder_full_name = elder_full_name

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if "intent" in system.lower():
            if f"Falo com {self.elder_first_name}" in prompt:
                return f'{{"intent": "TALK", "target": "{self.elder_full_name}"}}'
            return '{"intent": "FREEFORM", "target": null}'
        return "— Bom dia."

class PassiveLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return "A ação ocorre conforme determinado pelo sistema."

def test_direct_follow_up_keeps_npc_and_exact_recent_history(db_session):
    campaign, _region, _village, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.role == "ancião da vila").one()
    elder_first_name = osgar.name.split()[0]
    llm = ConversationLLM(elder_first_name, osgar.name)

    first = engine.resolve_action(
        db_session, llm, campaign.id, character.id, f"Falo com {elder_first_name}: — Bom dia."
    )
    assert elder_first_name not in first.narrative

    first_call_count = len(llm.calls)
    engine.resolve_action(
        db_session, llm, campaign.id, character.id, "— O senhor nasceu aqui?"
    )
    second_calls = llm.calls[first_call_count:]
    second_prompts = "\n".join(prompt for _system, prompt in second_calls)

    assert f"ACTIVE NPC CONTEXT\nName: {osgar.name}" in second_prompts
    assert "RELEVANT NPC MEMORIES" in second_prompts
    assert f"Hero lhe disse: Falo com {elder_first_name}" in second_prompts
    assert "Relationship with player: familiarity=1" in second_prompts

    relationship = db_session.query(CharacterNPCRelationship).one()
    assert relationship.familiarity == 2
    assert relationship.trust == 0
    assert relationship.affinity == 0
    assert (
        db_session.query(Memory)
        .filter(
            Memory.owner_type == MemoryOwnerType.PLAYER.value,
            Memory.owner_id == character.id,
        )
        .count()
        == 3
    )
    assert (
        db_session.query(Memory)
        .filter(
            Memory.owner_type == MemoryOwnerType.NPC.value,
            Memory.subject == f"character:{character.id}",
        )
        .count()
        == 3
    )
    assert f'O jogador disse anteriormente: "Falo com {elder_first_name}: — Bom dia."' in second_prompts
    assert 'Resposta narrada anteriormente: "— Bom dia."' in second_prompts

def test_resolve_action_move_advances_clock_and_world_tick_exactly_once(
    db_session,
    monkeypatch,
):
    campaign, region, village, character = _setup(db_session)

    forest = (
        db_session.query(Location)
        .filter(
            Location.subregion_id == village.subregion_id,
            Location.type == "forest",
        )
        .first()
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == forest.id,
        )
        .one()
    )

    connection.danger = 0

    discover_connection(
        db_session,
        character.id,
        connection.id,
    )

    set_location_discovery(
        db_session,
        character.id,
        forest.id,
        DiscoveryStatus.DISCOVERED,
    )

    expected_minutes = travel_service.calculate_travel_minutes(
        connection
    )

    start_time = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    tick_calls = []

    def fake_tick(db, campaign_id, minutes):
        tick_calls.append(
            (
                campaign_id,
                minutes,
            )
        )

    monkeypatch.setattr(
        engine.world_simulation,
        "tick",
        fake_tick,
    )

    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *args, **kwargs: Intent(
            type=ActionIntentType.MOVE,
            target=forest.name,
            raw_text="Vou até o bosque.",
        ),
    )

    engine.resolve_action(
        db_session,
        PassiveLLM(),
        campaign.id,
        character.id,
        "Vou até o bosque.",
    )

    end_time = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    assert end_time - start_time == expected_minutes

    assert tick_calls == [
        (
            campaign.id,
            expected_minutes,
        )
    ]

    assert character.location_id == forest.id

    time_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type
            == EventType.WORLD_TIME_ADVANCED.value,
        )
        .all()
    )

    assert len(time_events) == 1

    payload = json.loads(
        time_events[0].payload_json
    )

    assert payload["minutes"] == expected_minutes

def test_examine_narrator_receives_discoveries_in_same_turn(
    db_session,
    monkeypatch,
):
    campaign, region, village, character = _setup(db_session)

    forest = (
        db_session.query(Location)
        .filter(
            Location.subregion_id == village.subregion_id,
            Location.type == "forest",
        )
        .first()
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == forest.id,
        )
        .one()
    )

    # Antes de observar, nem a rota nem o destino são conhecidos.
    assert (
        get_connection_discovery(
            db_session,
            character.id,
            connection.id,
        )
        is None
    )

    assert (
        get_location_discovery(
            db_session,
            character.id,
            forest.id,
        )
        is None
    )

    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *args, **kwargs: Intent(
            type=ActionIntentType.EXAMINE,
            target=None,
            raw_text="Olho ao redor.",
        ),
    )

    captured = {}

    def fake_narrate(
        llm_service,
        mechanical_summary,
        context,
        player_input="",
        recent_history="",
    ):
        captured["mechanical_summary"] = mechanical_summary
        captured["context"] = context
        return "Os arredores ficam mais claros à observação."

    monkeypatch.setattr(
        engine.narrator,
        "narrate",
        fake_narrate,
    )

    engine.resolve_action(
        db_session,
        PassiveLLM(),
        campaign.id,
        character.id,
        "Olho ao redor.",
    )

    # O EXAMINE alterou o estado mecânico.
    connection_discovery = get_connection_discovery(
        db_session,
        character.id,
        connection.id,
    )

    location_discovery = get_location_discovery(
        db_session,
        character.id,
        forest.id,
    )

    assert connection_discovery is not None

    assert location_discovery is not None
    assert location_discovery.status == DiscoveryStatus.DISCOVERED

    # E o Narrator recebeu o contexto reconstruído DEPOIS da descoberta.
    fresh_context = captured["context"]

    assert "CONNECTED LOCATIONS KNOWN TO PLAYER" in fresh_context

    connection_section = fresh_context.split(
        "CONNECTED LOCATIONS KNOWN TO PLAYER",
        1,
    )[1].split(
        "PLAYER CURRENT LOCATION KNOWLEDGE",
        1,
    )[0]

    assert "noroeste -> Local desconhecido" in connection_section
    assert forest.name not in connection_section

    assert "PLAYER SPATIAL KNOWLEDGE" in fresh_context
    assert "Local desconhecido [DISCOVERED]" in fresh_context

def test_resolve_action_zero_minutes_does_not_advance_clock_or_tick(
    db_session,
    monkeypatch,
):
    campaign, region, village, character = _setup(db_session)

    start_time = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    initial_time_event_count = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type
            == EventType.WORLD_TIME_ADVANCED.value,
        )
        .count()
    )

    tick_calls = []

    def fake_tick(db, campaign_id, minutes):
        tick_calls.append(
            (
                campaign_id,
                minutes,
            )
        )

    monkeypatch.setattr(
        engine.world_simulation,
        "tick",
        fake_tick,
    )

    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *args, **kwargs: Intent(
            type=ActionIntentType.MOVE,
            target="Lugar Inexistente",
            raw_text="Vou até um lugar inexistente.",
        ),
    )

    engine.resolve_action(
        db_session,
        PassiveLLM(),
        campaign.id,
        character.id,
        "Vou até um lugar inexistente.",
    )

    end_time = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    assert end_time == start_time

    assert tick_calls == []

    final_time_event_count = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type
            == EventType.WORLD_TIME_ADVANCED.value,
        )
        .count()
    )

    assert final_time_event_count == initial_time_event_count
    assert character.location_id == village.id

def test_apply_intent_move_uses_requested_fast_pace(db_session):
    campaign, region, village, character = _setup(db_session)

    forest = (
        db_session.query(Location)
        .filter(
            Location.subregion_id == village.subregion_id,
            Location.type == "forest",
        )
        .first()
    )

    connection = (
        db_session.query(LocationConnection)
        .filter(
            LocationConnection.from_location_id == village.id,
            LocationConnection.to_location_id == forest.id,
        )
        .one()
    )

    connection.danger = 0

    discover_connection(
        db_session,
        character.id,
        connection.id,
    )

    set_location_discovery(
        db_session,
        character.id,
        forest.id,
        DiscoveryStatus.DISCOVERED,
    )

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    starting_stamina = character.stamina_current

    intent = Intent(
        type=ActionIntentType.MOVE,
        target=forest.name,
        raw_text="Corro até o bosque.",
        pace=TravelPace.FAST,
    )

    summary, minutes = engine._apply_intent(
        db_session,
        campaign.id,
        character,
        intent,
        state,
    )

    expected_minutes = travel_service.calculate_travel_minutes(
        connection,
        travel_service.PACE_SPEED_MULTIPLIERS[TravelPace.FAST],
    )

    expected_stamina = (
        travel_service.calculate_travel_stamina_cost(
            connection,
            TravelPace.FAST,
        )
    )

    assert minutes == expected_minutes
    assert character.location_id == forest.id
    assert character.stamina_current == (
        starting_stamina - expected_stamina
    )

def test_talk_keeps_action_interlocutor_when_npc_rests_during_action(
    db_session,
):
    campaign, _region, village, character = _setup(db_session)

    osgar = (
        db_session.query(NPC)
        .filter(
            NPC.campaign_id == campaign.id,
            NPC.role == "ancião da vila",
        )
        .one()
    )
    elder_first_name = osgar.name.split()[0]

    # O mundo começa às 08:00.
    # Leva o relógio até 21:59:59 sem iniciar uma ação.
    clock.advance_world_time(
        db_session,
        campaign.id,
        13 * 60 + 59,
    )

    clock.advance_world_time_seconds(
        db_session,
        campaign.id,
        59,
    )

    db_session.refresh(osgar)

    assert osgar.activity != NPCActivity.RESTING.value

    player_memories_before = (
        db_session.query(Memory)
        .filter(
            Memory.owner_type == MemoryOwnerType.PLAYER.value,
            Memory.owner_id == character.id,
        )
        .count()
    )

    npc_memories_before = (
        db_session.query(Memory)
        .filter(
            Memory.owner_type == MemoryOwnerType.NPC.value,
            Memory.owner_id == osgar.id,
            Memory.subject == f"character:{character.id}",
        )
        .count()
    )

    llm = ConversationLLM(elder_first_name, osgar.name)

    result = engine.resolve_action(
        db_session,
        llm,
        campaign.id,
        character.id,
        f"Falo com {elder_first_name}: — Boa noite.",
    )

    db_session.refresh(osgar)

    # A fala curta custa 3 segundos:
    # 21:59:59 -> 22:00:02.
    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    assert state.world_time.hour == 22
    assert state.world_time.minute == 0
    assert state.world_time.subminute_seconds == 2

    # O World Tick já colocou Osgar para descansar.
    assert osgar.activity == NPCActivity.RESTING.value

    # Portanto ele não está mais presente na cena atual.
    assert osgar.id not in {
        npc.id
        for npc in state.nearby_npcs
    }

    # E a conversa não permanece ativa para o próximo turno.
    assert (
        npcs_service.get_active_interlocutor(
            db_session,
            campaign.id,
            character.id,
            village.id,
        )
        is None
    )

    # Porém o Narrator deste turno ainda recebeu Osgar
    # como interlocutor da ação que acabou de acontecer.
    narrator_prompts = "\n".join(
        prompt
        for system, prompt in llm.calls
        if "intent" not in system.lower()
    )

    assert f"ACTIVE NPC CONTEXT\nName: {osgar.name}" in narrator_prompts
    assert "Current activity: RESTING" in narrator_prompts
    assert (
        "participated in the action that just occurred"
        in narrator_prompts
    )

    # A conversa continua sendo registrada como uma interação real,
    # mesmo que Osgar tenha ficado indisponível depois dela.
    relationship = (
        db_session.query(CharacterNPCRelationship)
        .filter(
            CharacterNPCRelationship.character_id
            == character.id,
            CharacterNPCRelationship.npc_id
            == osgar.id,
        )
        .one()
    )

    assert relationship.familiarity == 1

    player_memories_after = (
        db_session.query(Memory)
        .filter(
            Memory.owner_type == MemoryOwnerType.PLAYER.value,
            Memory.owner_id == character.id,
        )
        .count()
    )

    npc_memories_after = (
        db_session.query(Memory)
        .filter(
            Memory.owner_type == MemoryOwnerType.NPC.value,
            Memory.owner_id == osgar.id,
            Memory.subject == f"character:{character.id}",
        )
        .count()
    )

    assert player_memories_after > player_memories_before
    assert npc_memories_after > npc_memories_before

    assert result.intent_type == ActionIntentType.TALK.value

def test_talk_duration_scales_with_message_length():
    assert engine._estimate_talk_seconds(
        "Olá."
    ) == 2

    thirty_words = " ".join(
        ["palavra"] * 30
    )

    assert engine._estimate_talk_seconds(
        thirty_words
    ) == 12

    one_hundred_fifty_words = " ".join(
        ["palavra"] * 150
    )

    assert engine._estimate_talk_seconds(
        one_hundred_fifty_words
    ) == 60
