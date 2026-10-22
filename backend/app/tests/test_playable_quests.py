from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.core.enums import (
    ActionIntentType,
    NoticeStatus,
    ObjectiveTriggerType,
    QuestStatus,
)
from app.db.models.character import Character
from app.db.models.location import Location, LocationFeature
from app.db.models.notice import Notice
from app.db.models.npc import NPC
from app.db.models.organization import OrganizationNeed
from app.db.models.quest import CharacterQuest, Quest
from app.game import engine
from app.game.notices.service import read_notice_board
from app.game.quests.rewards import grant_pending_quest_completion_xp
from app.game.quests.service import evaluate_objective_trigger
from app.game.quests.initial_content import ensure_initial_quest_opportunities_for_campaign


class PassiveLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return "O resultado mecânico é narrado sem acrescentar fatos."


def _started_world(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Playable Quests"}).json()
    character_data = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    client.post(
        f"/api/campaigns/{campaign['id']}/start",
        params={"character_id": character_data["id"]},
    )
    character = db_session.get(Character, character_data["id"])
    return campaign, character


def _boards_and_locations(db_session):
    guild_board = (
        db_session.query(LocationFeature)
        .filter(LocationFeature.name == "Quadro de Contratos da Guilda")
        .one()
    )
    public_board = (
        db_session.query(LocationFeature)
        .filter(LocationFeature.name.like("Quadro de Avisos de %"))
        .one()
    )
    return guild_board, public_board


def test_initial_world_has_grounded_board_content_without_revealing_it_remotely(
    client, db_session
):
    campaign, character = _started_world(client, db_session)
    guild_board, public_board = _boards_and_locations(db_session)

    assert db_session.query(Quest).count() == 2
    assert db_session.query(OrganizationNeed).count() >= 2
    assert db_session.query(Notice).filter(Notice.board_feature_id == guild_board.id).count() == 2
    assert db_session.query(Notice).filter(Notice.board_feature_id == public_board.id).count() == 1

    hidden = client.get(
        f"/api/campaigns/{campaign['id']}/quests",
        params={"character_id": character.id},
    )
    assert hidden.json() == {"quests": []}

    character.location_id = guild_board.location_id
    read_notice_board(db_session, character.id, guild_board.id)
    db_session.commit()

    revealed = client.get(
        f"/api/campaigns/{campaign['id']}/quests",
        params={"character_id": character.id},
    ).json()["quests"]
    assert {quest["name"] for quest in revealed} == {
        "Relato da Primeira Chegada",
        "Ronda dos Avisos",
    }
    assert {quest["status"] for quest in revealed} == {QuestStatus.AVAILABLE}


def test_initial_opportunity_backfill_is_idempotent(client, db_session):
    campaign, _character = _started_world(client, db_session)
    quest_count = db_session.query(Quest).count()
    notice_count = db_session.query(Notice).count()

    created = ensure_initial_quest_opportunities_for_campaign(
        db_session, campaign["id"]
    )

    assert created is False
    assert db_session.query(Quest).count() == quest_count
    assert db_session.query(Notice).count() == notice_count


def test_accept_endpoint_claims_the_real_contract_notice(client, db_session):
    campaign, character = _started_world(client, db_session)
    guild_board, _public_board = _boards_and_locations(db_session)
    character.location_id = guild_board.location_id
    read_notice_board(db_session, character.id, guild_board.id)
    quest = db_session.query(Quest).filter(Quest.name == "Relato da Primeira Chegada").one()
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign['id']}/quests/{quest.id}/accept",
        params={"character_id": character.id},
    )

    assert response.status_code == 200
    assert response.json()["status"] == QuestStatus.ACTIVE
    participation = db_session.query(CharacterQuest).filter_by(
        character_id=character.id, quest_id=quest.id
    ).one()
    assert participation.status == QuestStatus.ACTIVE
    notice = db_session.query(Notice).filter(Notice.quest_id == quest.id).one()
    assert notice.status == NoticeStatus.CLAIMED


def test_two_initial_contracts_complete_from_real_triggers_and_reach_level_one(
    client, db_session
):
    campaign, character = _started_world(client, db_session)
    guild_board, public_board = _boards_and_locations(db_session)
    character.location_id = guild_board.location_id
    read_notice_board(db_session, character.id, guild_board.id)
    quests = {quest.name: quest for quest in db_session.query(Quest).all()}
    for quest in quests.values():
        response = client.post(
            f"/api/campaigns/{campaign['id']}/quests/{quest.id}/accept",
            params={"character_id": character.id},
        )
        assert response.status_code == 200

    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").one()
    guildmaster = db_session.query(NPC).filter(
        NPC.role == "mestre da guilda de aventureiros"
    ).one()
    evaluate_objective_trigger(
        db_session,
        campaign["id"],
        character.id,
        ObjectiveTriggerType.TALK_TO_NPC,
        subject_id=elder.id,
    )

    character.location_id = public_board.location_id
    summary, _minutes = engine._handle_examine(
        db_session,
        campaign["id"],
        character,
        Intent(
            type=ActionIntentType.EXAMINE,
            target="Quadro de Avisos",
            raw_text="Leio o quadro de avisos",
        ),
    )
    assert "lê o Quadro de Avisos" in summary

    evaluate_objective_trigger(
        db_session,
        campaign["id"],
        character.id,
        ObjectiveTriggerType.TALK_TO_NPC,
        subject_id=guildmaster.id,
    )
    rewards = grant_pending_quest_completion_xp(
        db_session, PassiveLLM(), campaign["id"], character
    )

    assert {name: amount for name, amount in rewards} == {
        "Relato da Primeira Chegada": 10.0,
        "Ronda dos Avisos": 15.0,
    }
    assert character.level == 1
    assert character.xp == 0
    assert {
        participation.status for participation in db_session.query(CharacterQuest).all()
    } == {QuestStatus.COMPLETED}
    assert {
        notice.status
        for notice in db_session.query(Notice).filter(Notice.quest_id.isnot(None)).all()
    } == {NoticeStatus.COMPLETED}


def test_undo_restores_quest_acceptance_knowledge_and_notice_state(
    client, db_session, fake_llm
):
    campaign, character = _started_world(client, db_session)
    guild_board, _public_board = _boards_and_locations(db_session)
    character.location_id = guild_board.location_id
    read_notice_board(db_session, character.id, guild_board.id)
    db_session.commit()

    accepted = client.post(
        f"/api/campaigns/{campaign['id']}/actions",
        params={"character_id": character.id},
        json={
            "text": "Aceito a missão Relato da Primeira Chegada",
            "action_key": "accept-first-contract",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["intent_type"] == ActionIntentType.ACCEPT_QUEST
    assert db_session.query(CharacterQuest).count() == 1

    undone = client.post(
        f"/api/campaigns/{campaign['id']}/actions/undo-last",
        params={"character_id": character.id},
        json={"reason": "Quero escolher outro contrato."},
    )
    assert undone.status_code == 200
    assert db_session.query(CharacterQuest).count() == 0
    notice = (
        db_session.query(Notice)
        .join(Quest, Quest.id == Notice.quest_id)
        .filter(Quest.name == "Relato da Primeira Chegada")
        .one()
    )
    assert notice.status == NoticeStatus.ACTIVE
