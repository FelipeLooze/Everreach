from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.core.enums import ActionIntentType, DiscoveryStatus, MemoryOwnerType
from app.core.enums import EventType
from app.db.models.npc import NPC
from app.db.models.location import Location
from app.db.models.quest import CharacterQuestObjective
from app.db.models.memory import Memory
from app.db.models.relationship import CharacterNPCRelationship
from app.game import engine
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.quests.service import start_quest
from app.game.world.seed import create_campaign, seed_initial_region
from app.db.models.quest import Quest, QuestObjective
from app.game.npcs import service as npcs_service
from app.services.event_log import log_event
from app.game.discovery.service import (
    get_location_discovery,
    set_location_discovery,
)

def _setup(db_session):
    campaign = create_campaign(db_session, "Intent Test")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.commit()
    return campaign, region, village, character


def test_apply_intent_move_relocates_character(db_session):
    campaign, region, village, character = _setup(db_session)
    forest = db_session.query(Location).filter(Location.region_id == region.id, Location.type == "forest").first()
    set_location_discovery(
        db_session,
        character.id,
        forest.id,
        DiscoveryStatus.DISCOVERED,
    )
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.MOVE, target="Bosque da Beira do Vale", raw_text="I walk to the forest")
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert minutes > 0
    assert "Bosque da Beira do Vale" in summary
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
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.MOVE, target="Bosque da Beira do Vale", raw_text="Vou ao bosque")
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert minutes == 0
    assert "Nenhum lugar conhecido" in summary
    assert character.location_id == village.id


def test_apply_intent_talk_completes_matching_quest_objective(db_session):
    campaign, region, village, character = _setup(db_session)

    quest = Quest(
        region_id=region.id,
        name="Falar com o Ancião",
        description="Quest criada exclusivamente para testar objetivos de conversa.",
    )
    db_session.add(quest)
    db_session.flush()

    objective = QuestObjective(
        quest_id=quest.id,
        description="Falar com Osgar Vell em Cardal.",
        order=0,
    )
    db_session.add(objective)
    db_session.flush()

    start_quest(db_session, character.id, quest.id)

    
    db_session.commit()

    state = build_game_state(db_session, campaign.id, character.id)
    intent = Intent(type=ActionIntentType.TALK, target="Osgar Vell", raw_text="I talk to Osgar Vell")
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert "Osgar Vell" in summary
    assert minutes > 0

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
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if "intent" in system.lower():
            if "Falo com Osgar" in prompt:
                return '{"intent": "TALK", "target": "Osgar Vell"}'
            return '{"intent": "FREEFORM", "target": null}'
        return "— Bom dia."


def test_direct_follow_up_keeps_npc_and_exact_recent_history(db_session):
    campaign, _region, _village, character = _setup(db_session)
    llm = ConversationLLM()

    first = engine.resolve_action(
        db_session, llm, campaign.id, character.id, "Falo com Osgar: — Bom dia."
    )
    assert "Osgar" not in first.narrative

    first_call_count = len(llm.calls)
    engine.resolve_action(
        db_session, llm, campaign.id, character.id, "— O senhor nasceu aqui?"
    )
    second_calls = llm.calls[first_call_count:]
    second_prompts = "\n".join(prompt for _system, prompt in second_calls)

    assert "ACTIVE NPC CONTEXT\nName: Osgar Vell" in second_prompts
    assert "RELEVANT NPC MEMORIES" in second_prompts
    assert "Hero lhe disse: Falo com Osgar" in second_prompts
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
    assert "PLAYER: Falo com Osgar: — Bom dia." in second_prompts
    assert "NARRATOR: — Bom dia." in second_prompts
