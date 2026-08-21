"""Phase 12H — Emergent World Quests.

WORLD FIRST, QUEST SECOND: propose_emergent_quest_from_npc_death never
invents that something happened — it only ever runs against an already-
logged, real WorldEvent (NPC_DIED). The LLM only phrases; a proposal
inventing a name, culprit, or numeric reward the event never established
is rejected and the function falls back to a plain backend-authored
identity rather than failing outright, since the underlying event already
justifies the Quest existing.
"""

from app.ai.llm_service import LLMService, LLMServiceError
from app.core.enums import EventType, QuestSource
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.quests.emergence import EmergentQuestError, propose_emergent_quest_from_npc_death
from app.game.world.seed import create_campaign, seed_initial_region
from app.services.event_log import log_event


class ScriptedLLM(LLMService):
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def generate(self, system: str, prompt: str) -> str:
        self.calls += 1
        return self.response


class UnavailableLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        raise LLMServiceError("Ollama indisponível.")


def _setup(db_session):
    campaign = create_campaign(db_session, "Quest Emergence")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, character


def _log_npc_death(db_session, campaign, npc, cause="combate"):
    npc.alive = False
    event = log_event(
        db_session,
        campaign.id,
        EventType.NPC_DIED,
        actor_type="npc",
        actor_id=npc.id,
        payload={"npc_id": npc.id, "name": npc.name, "cause": cause},
        importance=5,
    )
    db_session.commit()
    return event


def test_valid_proposal_grounded_in_the_event_is_accepted(db_session):
    campaign, region, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    event = _log_npc_death(db_session, campaign, osgar)
    llm = ScriptedLLM(
        '{"name": "A morte de Osgar Vell", '
        '"description": "Osgar Vell morreu em Cardal. Alguém pode querer saber o que houve."}'
    )

    quest = propose_emergent_quest_from_npc_death(
        db_session, campaign.id, llm, world_event_id=event.id
    )

    assert quest.name == "A morte de Osgar Vell"
    assert quest.source == QuestSource.WORLD_EVENT
    assert quest.source_event_id == event.id
    assert llm.calls == 1


def test_proposal_inventing_an_unknown_name_is_rejected_then_falls_back(db_session):
    campaign, region, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    event = _log_npc_death(db_session, campaign, osgar)
    llm = ScriptedLLM(
        '{"name": "A conspiração da Guilda das Sombras", '
        '"description": "A Guilda das Sombras matou Osgar Vell."}'
    )

    quest = propose_emergent_quest_from_npc_death(
        db_session, campaign.id, llm, world_event_id=event.id
    )

    assert quest.name == "A morte de Osgar Vell"
    assert "Osgar Vell morreu" in quest.description
    assert llm.calls == 2  # both attempts consumed, both rejected


def test_proposal_inventing_a_numeric_reward_is_rejected_then_falls_back(db_session):
    campaign, region, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    event = _log_npc_death(db_session, campaign, osgar)
    llm = ScriptedLLM(
        '{"name": "A morte de Osgar Vell", '
        '"description": "Osgar Vell morreu. Há 50 moedas de recompensa por informações."}'
    )

    quest = propose_emergent_quest_from_npc_death(
        db_session, campaign.id, llm, world_event_id=event.id
    )

    assert quest.description == f"{osgar.name} morreu (combate). Alguém pode querer entender o que houve."


def test_unavailable_llm_falls_back_to_backend_authored_identity(db_session):
    campaign, region, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    event = _log_npc_death(db_session, campaign, osgar)

    quest = propose_emergent_quest_from_npc_death(
        db_session, campaign.id, UnavailableLLM(), world_event_id=event.id
    )

    assert quest.name == "A morte de Osgar Vell"
    assert quest.source_event_id == event.id


def test_is_idempotent_per_source_event(db_session):
    campaign, region, character = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    event = _log_npc_death(db_session, campaign, osgar)
    llm = ScriptedLLM('{"name": "A morte de Osgar Vell", "description": "Osgar Vell morreu."}')

    first = propose_emergent_quest_from_npc_death(
        db_session, campaign.id, llm, world_event_id=event.id
    )
    second = propose_emergent_quest_from_npc_death(
        db_session, campaign.id, llm, world_event_id=event.id
    )

    assert first.id == second.id
    assert llm.calls == 1


def test_rejects_a_non_quest_worthy_event_type(db_session):
    campaign, region, character = _setup(db_session)
    event = log_event(db_session, campaign.id, EventType.WORLD_TIME_ADVANCED, actor_type="world")
    db_session.commit()

    try:
        propose_emergent_quest_from_npc_death(
            db_session, campaign.id, ScriptedLLM("{}"), world_event_id=event.id
        )
        assert False, "expected EmergentQuestError"
    except EmergentQuestError:
        pass


def test_rejects_an_unknown_event_id(db_session):
    campaign, region, character = _setup(db_session)

    try:
        propose_emergent_quest_from_npc_death(
            db_session, campaign.id, ScriptedLLM("{}"), world_event_id="evt_nonexistent"
        )
        assert False, "expected EmergentQuestError"
    except EmergentQuestError:
        pass
