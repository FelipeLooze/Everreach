"""Starting village, part 4: villagers' own requests — learned by talking,
accepted by saying yes, completed from real state (reaching a place,
picking an item up, handing it over), paid from the villager's purse."""

import json

from app.ai.llm_service import LLMService
from app.core.enums import CombatActorType, KnowerType, QuestStatus
from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.quest import CharacterQuest, Quest
from app.db.models.relationship import CharacterNPCRelationship
from app.game import engine
from app.game.economy.wallet import total_carried_by_owner
from app.game.npcs import profile
from app.game.npcs.service import knows
from app.game.quests.discovery import is_quest_known_to_character
from app.game.quests.service import quest_existence_fact_key
from app.game.time import clock
from app.simulation import npc_simulation

DAY = 24 * 60


class ScriptedLLM(LLMService):
    """Intent JSON for each player line, in order; any other prompt is the
    narrator, who says what the test hands it."""

    def __init__(self, intents, narration):
        self.intents = list(intents)
        self.narration = narration

    def generate(self, system, prompt):
        if "Ação do jogador" in prompt:
            return json.dumps(self.intents.pop(0))
        return self.narration


def _start(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Pedidos"}).json()
    data = client.post(f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}).json()
    client.post(f"/api/campaigns/{campaign['id']}/start", params={"character_id": data["id"]})
    return campaign["id"], db_session.get(Character, data["id"])


def _npc(db_session, campaign_id, prefix):
    return next(npc for npc in db_session.query(NPC).filter(NPC.campaign_id == campaign_id)
                if npc.role.startswith(prefix))


def _act(db_session, campaign_id, character, text, intent, narration="— Hum."):
    llm = ScriptedLLM([intent], narration)
    return engine.resolve_action(db_session, llm, campaign_id, character.id, text, intent_llm_service=llm)


def _ref(db_session, campaign_id, character, npc):
    """How the intent parser points at someone present: P1, P2…"""
    from app.ai.people_present import present_people
    from app.game.game_state import build_game_state

    people = present_people(build_game_state(db_session, campaign_id, character.id))
    return f"P{[person.id for _kind, person in people].index(npc.id) + 1}"


def _set_hour(db_session, campaign_id, hour):
    now = clock.get_world_time(db_session, campaign_id).total_minutes()
    clock.advance_world_time(db_session, campaign_id, (now // DAY + 1) * DAY + hour * 60 - now)
    npc_simulation.tick(db_session, campaign_id, 1)  # residents move with the clock


def test_each_request_is_known_only_to_the_villager_who_asks_it(client, db_session):
    campaign_id, character = _start(client, db_session)
    requests = db_session.query(Quest).filter(Quest.giver_npc_id.is_not(None)).all()
    assert len(requests) == 7

    for quest in requests:
        giver = db_session.get(NPC, quest.giver_npc_id)
        assert knows(db_session, KnowerType.NPC, giver.id, quest_existence_fact_key(quest.id), campaign_id)
        assert not is_quest_known_to_character(db_session, campaign_id, character.id, quest.id)
        assert total_carried_by_owner(db_session, CombatActorType.NPC, giver.id) >= quest.reward_bronze
        assert "Has a favour to ask" in " ".join(profile.context_lines(db_session, giver, trust=0))


def test_the_herbalist_request_from_asking_to_payment(client, db_session):
    campaign_id, character = _start(client, db_session)
    herbalist = _npc(db_session, campaign_id, "herbalista")
    quest = db_session.query(Quest).filter(Quest.giver_npc_id == herbalist.id).one()
    river = db_session.get(Location, herbalist.workplace_location_id)
    _set_hour(db_session, campaign_id, 7)  # she gathers at the river until 10
    character.location_id = river.id
    db_session.commit()

    _act(db_session, campaign_id, character, '"Bom dia. Posso ajudar a senhora em alguma coisa?"',
         {"intent": "TALK", "target": herbalist.name},
         narration="— As ervas para a febre estão acabando. Preciso de um ramo da beira do riacho.")
    assert is_quest_known_to_character(db_session, campaign_id, character.id, quest.id)

    _act(db_session, campaign_id, character, '"Pode deixar, eu busco a erva para a senhora."',
         {"intent": "TALK", "target": herbalist.name})
    assert db_session.query(CharacterQuest).filter_by(character_id=character.id, quest_id=quest.id).one().status == QuestStatus.ACTIVE

    _act(db_session, campaign_id, character, "Colho o ramo de erva-de-febre",
         {"intent": "PICK_UP", "target": "Ramo de erva-de-febre"})
    bronze_before = total_carried_by_owner(db_session, CombatActorType.CHARACTER, character.id)
    result = _act(db_session, campaign_id, character, "Entrego o ramo de erva para a herbalista",
                  {"intent": "GIVE", "target": "Ramo de erva-de-febre", "secondary_target": "herbalista"})

    db_session.refresh(quest)
    assert quest.status == QuestStatus.COMPLETED, result.mechanical_summary
    assert total_carried_by_owner(db_session, CombatActorType.CHARACTER, character.id) == bronze_before + quest.reward_bronze
    trust = db_session.query(CharacterNPCRelationship).filter_by(character_id=character.id, npc_id=herbalist.id).one().trust
    assert trust >= profile.SECRET_TRUST
    assert f"paga {quest.reward_bronze} bronze" in result.mechanical_summary


def test_reaching_the_forest_and_reporting_back_completes_the_hunters_request(client, db_session):
    campaign_id, character = _start(client, db_session)
    hunter = _npc(db_session, campaign_id, "caçador")
    quest = db_session.query(Quest).filter(Quest.giver_npc_id == hunter.id).one()
    forest = db_session.get(Location, hunter.workplace_location_id)
    village_id = character.location_id
    _set_hour(db_session, campaign_id, 12)  # lunch in the square
    db_session.commit()

    _act(db_session, campaign_id, character, '"O que anda te preocupando?"', {"intent": "TALK", "person": _ref(db_session, campaign_id, character, hunter)},
         narration="— As armadilhas do bosque. Ninguém conferiu desde que vocês chegaram.")
    _act(db_session, campaign_id, character, '"Deixa comigo, eu vou lá ver."', {"intent": "TALK", "person": _ref(db_session, campaign_id, character, hunter)})
    assert db_session.query(CharacterQuest).filter_by(character_id=character.id, quest_id=quest.id).one()

    # Accepting taught the way there: no manual discovery needed.
    moved = _act(db_session, campaign_id, character, f"Vou até {forest.name}", {"intent": "MOVE", "target": forest.name})
    assert character.location_id == forest.id, moved.mechanical_summary
    _act(db_session, campaign_id, character, "Volto para a praça", {"intent": "MOVE", "target": "praça"})
    assert character.location_id == village_id
    _set_hour(db_session, campaign_id, 12)
    db_session.commit()
    _act(db_session, campaign_id, character, '"As armadilhas estão de pé."', {"intent": "TALK", "person": _ref(db_session, campaign_id, character, hunter)})

    db_session.refresh(quest)
    assert quest.status == QuestStatus.COMPLETED


def test_a_question_never_accepts_and_nothing_untold_can_be_accepted(client, db_session):
    campaign_id, character = _start(client, db_session)
    old_woman = _npc(db_session, campaign_id, "velh")
    _set_hour(db_session, campaign_id, 9)
    db_session.commit()

    assert engine._accept_request_by_agreement(db_session, campaign_id, character, old_woman, "Pode deixar")[0] is None
    quest = db_session.query(Quest).filter(Quest.giver_npc_id == old_woman.id).one()
    from app.game.quests.discovery import learn_about_quest_from_npc
    learn_about_quest_from_npc(db_session, campaign_id, character.id, quest.id)
    assert engine._accept_request_by_agreement(db_session, campaign_id, character, old_woman, "Pode deixar?")[0] is None
    accepted, way = engine._accept_request_by_agreement(db_session, campaign_id, character, old_woman, "Pode deixar, eu procuro.")
    assert accepted == quest and [place.type for place in way] == ["clearing"]
