import random
import json

from app.core.enums import (
    SimulatedPlayerActivity,
    SimulatedPlayerStatus,
)
from app.game.players.encounter import (
    resolve_simulated_player_encounter,
)
from app.game.relationships.service import (
    get_character_simulated_player_relationship,
    record_simulated_player_interaction,
)
from app.ai.llm_service import LLMService
from app.db.models.event import WorldEvent
from app.game.players.service import (
    get_active_simulated_player_interlocutor,
    meet_simulated_player,
    select_existing_simulated_player_for_encounter,
    simulated_players_at_location,
    abstract_simulated_player_count_at_location,
    set_abstract_simulated_player_population,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)
from app.core.enums import (
    EventType, 
    ActionIntentType, 
    MemoryOwnerType,
)
from app.ai.intent_parser import Intent
from app.game import engine
from app.game.game_state import build_game_state
from app.ai.context_builder import build_context
from app.db.models.memory import Memory

class EncounterMaterializationLLM(LLMService):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(
        self,
        system: str,
        prompt: str,
    ) -> str:
        self.calls.append(
            (system, prompt)
        )

        return json.dumps(
            {
                "name": "Kaelen Voss",
                "personality": (
                    "Calmo, prudente e observador."
                ),
                "background": (
                    "Trabalhava como técnico antes "
                    "de ser transportado."
                ),
                "motivation": (
                    "Encontrar estabilidade."
                ),
                "physical_description": (
                    "Homem jovem de cabelos escuros, "
                    "olhos castanhos e porte magro."
                ),
                "goal": (
                    "Encontrar trabalho e um lugar "
                    "seguro para viver."
                ),
                "archetype": "SOCIAL",
            }
        )

def test_conversation_creates_memories_and_relationship_with_transported_person(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Transported Dialogue Memory",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    from app.game.character.service import (
        create_character,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Logan",
        region.id,
        location.id,
    )

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    assert state.nearby_simulated_players

    transported = (
        state.nearby_simulated_players[0]
    )

    llm = TransportedConversationLLM(
        transported.name
    )

    engine.resolve_action(
        db_session,
        llm,
        campaign.id,
        character.id,
        f"Falo com {transported.name}.",
    )

    player_memories = (
        db_session.query(Memory)
        .filter(
            Memory.owner_type
            == MemoryOwnerType.PLAYER.value,
            Memory.owner_id
            == character.id,
            Memory.subject
            == f"simulated_player:{transported.id}",
        )
        .all()
    )

    transported_memories = (
        db_session.query(Memory)
        .filter(
            Memory.owner_type
            == MemoryOwnerType.SIMULATED_PLAYER.value,
            Memory.owner_id
            == transported.id,
            Memory.subject
            == f"character:{character.id}",
        )
        .all()
    )

    assert player_memories
    assert transported_memories

    assert transported.name in (
        player_memories[-1].summary_text
    )

    assert character.name in (
        transported_memories[-1].summary_text
    )

    relationship = (
        get_character_simulated_player_relationship(
            db_session,
            campaign.id,
            character.id,
            transported.id,
        )
    )

    assert relationship is not None
    assert relationship.familiarity == 1
    assert relationship.trust == 0
    assert relationship.affinity == 0

def test_encounter_reuses_existing_transported_person(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Existing Encounter",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    before = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert before

    before_ids = {
        player.id
        for player in before
    }

    selected = (
        select_existing_simulated_player_for_encounter(
            db_session,
            campaign.id,
            location.id,
            rng=random.Random(42),
        )
    )

    after = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert selected is not None
    assert selected.id in before_ids

    assert {
        player.id
        for player in after
    } == before_ids

def test_simulated_player_conversation_becomes_active(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Transported Conversation",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    from app.game.character.service import (
        create_character,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Logan",
        _region.id,
        location.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    assert players

    player = players[0]

    met = meet_simulated_player(
        db_session,
        campaign.id,
        character.id,
        player.id,
    )

    active = (
        get_active_simulated_player_interlocutor(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert met.id == player.id

    assert active is not None
    assert active.id == player.id

    event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id
            == campaign.id,
            WorldEvent.actor_id
            == character.id,
            WorldEvent.event_type
            == EventType.PLAYER_MET_SIMULATED_PLAYER.value,
        )
        .one()
    )

    assert event is not None

def test_talk_intent_can_target_simulated_player(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Talk To Transported",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    from app.game.character.service import (
        create_character,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Logan",
        region.id,
        location.id,
    )

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    assert state.nearby_simulated_players

    transported = (
        state.nearby_simulated_players[0]
    )

    intent = Intent(
        type=ActionIntentType.TALK,
        target=transported.name,
        raw_text=(
            f"Eu falo com {transported.name}."
        ),
    )

    summary, minutes = engine._apply_intent(
        db_session,
        campaign.id,
        character,
        intent,
        state,
    )

    assert transported.name in summary
    assert minutes == 0

    active = (
        get_active_simulated_player_interlocutor(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
    )

    assert active is not None
    assert active.id == transported.id

def test_active_simulated_player_has_private_identity_context(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Transported Private Context",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    from app.game.character.service import (
        create_character,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Logan",
        region.id,
        location.id,
    )

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    assert state.nearby_simulated_players

    transported = (
        state.nearby_simulated_players[0]
    )

    transported.personality = (
        "Calmo, desconfiado e observador."
    )
    transported.background = (
        "Trabalhava como mecânico antes da Chegada."
    )
    transported.motivation = (
        "Encontrar alguma estabilidade."
    )
    transported.goal = (
        "Conseguir trabalho e um lugar para morar."
    )
    transported.physical_description = (
        "Homem jovem de cabelos escuros e olhos castanhos."
    )

    db_session.flush()

    record_simulated_player_interaction(
        db_session,
        campaign.id,
        character.id,
        transported.id,
        familiarity_delta=7,
        trust_delta=60,
        affinity_delta=-60,
    )

    context = build_context(
        db_session,
        state,
        player_input="Quem é você?",
        active_simulated_player=transported.id,
    )

    assert "ACTIVE TRANSPORTED PERSON CONTEXT" in context
    assert transported.name in context
    assert "Calmo, desconfiado e observador." in context
    assert "Trabalhava como mecânico antes da Chegada." in context
    assert "Encontrar alguma estabilidade." in context
    assert "Conseguir trabalho e um lugar para morar." in context
    assert (
        "Homem jovem de cabelos escuros e olhos castanhos."
        in context
    )

    assert (
        "Relationship with player: "
        "familiarity=7, trust=60, affinity=-60"
        in context
    )

    assert (
        "Relationship behavior guidance "
        "(private narrator constraint):"
        in context
    )

    assert "Strong trust" in context

    assert "Strong negative affinity" in context

    assert (
        "never override personality, goals, safety"
        in context
    )

class TransportedConversationLLM(
    LLMService,
):
    def __init__(
        self,
        target_name: str,
    ) -> None:
        self.target_name = target_name
        self.calls: list[tuple[str, str]] = []

    def generate(
        self,
        system: str,
        prompt: str,
    ) -> str:
        self.calls.append(
            (system, prompt)
        )

        if "intent" in system.casefold():
            return (
                "{"
                '"intent": "TALK", '
                f'"target": "{self.target_name}"'
                "}"
            )

        return "— Olá."

def test_resolve_action_sends_active_transported_identity_to_narrator(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Transported Narrator Context",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    from app.game.character.service import (
        create_character,
    )

    character = create_character(
        db_session,
        campaign.id,
        "Logan",
        region.id,
        location.id,
    )

    state = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    assert state.nearby_simulated_players

    transported = (
        state.nearby_simulated_players[0]
    )

    transported.personality = (
        "Paciente e observador."
    )
    transported.background = (
        "Trabalhava como mecânico na Terra."
    )
    transported.motivation = (
        "Encontrar estabilidade."
    )
    transported.goal = (
        "Conseguir um lugar seguro para viver."
    )
    transported.physical_description = (
        "Homem jovem de cabelos escuros."
    )

    db_session.flush()

    state.world_time.hour = 21
    state.world_time.minute = 59
    state.world_time.subminute_seconds = 59

    db_session.flush()

    llm = TransportedConversationLLM(
        transported.name
    )

    result = engine.resolve_action(
        db_session,
        llm,
        campaign.id,
        character.id,
        f"Falo com {transported.name}.",
    )

    assert result.intent_type == ActionIntentType.TALK.value

    db_session.refresh(transported)

    state_after = build_game_state(
        db_session,
        campaign.id,
        character.id,
    )

    assert state_after.world_time.hour == 22
    assert state_after.world_time.minute == 0
    assert state_after.world_time.subminute_seconds == 1

    assert (
        transported.activity
        == SimulatedPlayerActivity.RESTING.value
    )

    assert transported.id not in {
        player.id
        for player in state_after.nearby_simulated_players
    }

    assert (
        get_active_simulated_player_interlocutor(
            db_session,
            campaign.id,
            character.id,
            location.id,
        )
        is None
    )

    narrator_prompts = [
        prompt
        for system, prompt in llm.calls
        if "SCENE CONTEXT:" in prompt
    ]

    assert narrator_prompts

    narrator_prompt = narrator_prompts[-1]

    assert (
        "ACTIVE TRANSPORTED PERSON CONTEXT"
        in narrator_prompt
    )
    assert transported.name in narrator_prompt
    assert "Paciente e observador." in narrator_prompt
    assert "Trabalhava como mecânico na Terra." in narrator_prompt

    assert (
        "Current activity: RESTING"
        in narrator_prompt
    )

    assert (
        "participated in the action that just occurred"
        in narrator_prompt
    )

    assert (
        "do not continue the conversation afterward"
        in narrator_prompt
    )

def test_encounter_reuses_persistent_person_before_materializing_new_one(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Encounter Priority",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    set_abstract_simulated_player_population(
        db_session,
        campaign.id,
        location.id,
        1,
    )

    existing_players = (
        simulated_players_at_location(
            db_session,
            location.id,
        )
    )

    assert existing_players

    existing_ids = {
        player.id
        for player in existing_players
    }

    llm = EncounterMaterializationLLM()

    resolved_existing = (
        resolve_simulated_player_encounter(
            db_session,
            llm,
            campaign.id,
            location.id,
            rng=random.Random(42),
        )
    )

    assert resolved_existing is not None
    assert resolved_existing.id in existing_ids

    assert len(llm.calls) == 0

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 1
    )

    for player in existing_players:
        player.status = (
            SimulatedPlayerStatus.DEAD.value
        )

    db_session.flush()

    resolved_new = (
        resolve_simulated_player_encounter(
            db_session,
            llm,
            campaign.id,
            location.id,
            rng=random.Random(42),
        )
    )

    assert resolved_new is not None
    assert resolved_new.id not in existing_ids
    assert resolved_new.name == "Kaelen Voss"

    assert len(llm.calls) == 1

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 0
    )

def test_encounter_returns_none_when_no_persistent_or_abstract_population(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Empty Encounter",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    existing_players = simulated_players_at_location(
        db_session,
        location.id,
    )

    for player in existing_players:
        player.status = SimulatedPlayerStatus.DEAD.value

    set_abstract_simulated_player_population(
        db_session,
        campaign.id,
        location.id,
        0,
    )

    db_session.flush()

    llm = EncounterMaterializationLLM()

    resolved = resolve_simulated_player_encounter(
        db_session,
        llm,
        campaign.id,
        location.id,
        rng=random.Random(42),
    )

    assert resolved is None
    assert len(llm.calls) == 0

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 0
    )    