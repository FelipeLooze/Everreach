import json
from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.core.enums import (
    ActionIntentType,
    CombatActorType,
    NoticeCategory,
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
from app.game.organizations.reputation import (
    organization_reputation_category,
    organization_reputation_history,
    organization_reputation_score,
)


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

    assert db_session.query(Quest).filter(Quest.giver_npc_id.is_(None)).count() == 2
    assert db_session.query(Quest).filter(Quest.giver_npc_id.is_not(None)).count() == 7  # villagers' own
    assert db_session.query(OrganizationNeed).count() >= 2
    assert db_session.query(Notice).filter(Notice.board_feature_id == guild_board.id).count() == 2
    public_notices = db_session.query(Notice).filter(
        Notice.board_feature_id == public_board.id
    )
    assert public_notices.filter(
        Notice.category == NoticeCategory.COMMUNITY_NOTICE.value
    ).count() == 1
    assert public_notices.filter(
        Notice.category == NoticeCategory.JOB.value
    ).count() == 3

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
    # The guild's two contracts; villagers' own requests are learned by talking.
    quests = {quest.name: quest for quest in db_session.query(Quest).filter(Quest.giver_npc_id.is_(None))}
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
    sponsor_id = quests["Relato da Primeira Chegada"].sponsoring_organization_id
    assert sponsor_id is not None
    assert organization_reputation_score(
        db_session, sponsor_id, CombatActorType.CHARACTER, character.id
    ) == 5
    assert organization_reputation_category(5) == "RELIABLE"
    assert len(
        organization_reputation_history(
            db_session, sponsor_id, CombatActorType.CHARACTER, character.id
        )
    ) == 2

    # Reward delivery and its organizational consequence share the same
    # CharacterQuest idempotency boundary.
    assert grant_pending_quest_completion_xp(
        db_session, PassiveLLM(), campaign["id"], character
    ) == []
    assert organization_reputation_score(
        db_session, sponsor_id, CombatActorType.CHARACTER, character.id
    ) == 5


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


def _accept_both_initial_contracts(db_session, campaign, character):
    from app.game.quests.discovery import learn_about_quest_from_notice
    from app.game.quests.service import accept_known_quest

    quests = db_session.query(Quest).filter(Quest.name.in_(
        ("Relato da Primeira Chegada", "Ronda dos Avisos")
    )).all()
    for quest in quests:
        learn_about_quest_from_notice(db_session, campaign["id"], character.id, quest.id)
        accept_known_quest(db_session, campaign["id"], character.id, quest.id)
    db_session.flush()
    return {quest.name: quest for quest in quests}


def test_delivery_objective_waits_for_the_report_it_delivers(client, db_session):
    # Audit: talking to the guildmaster BEFORE the elder ticked "leve o relato"
    # and the quest then paid out on the elder conversation instead.
    campaign, character = _started_world(client, db_session)
    quests = _accept_both_initial_contracts(db_session, campaign, character)
    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").one()
    guildmaster = db_session.query(NPC).filter(
        NPC.role == "mestre da guilda de aventureiros"
    ).one()

    early = evaluate_objective_trigger(
        db_session, campaign["id"], character.id,
        ObjectiveTriggerType.TALK_TO_NPC, subject_id=guildmaster.id,
    )
    assert early == []

    def participation(name):
        db_session.expire_all()
        return db_session.query(CharacterQuest).filter(
            CharacterQuest.character_id == character.id,
            CharacterQuest.quest_id == quests[name].id,
        ).one().status

    evaluate_objective_trigger(
        db_session, campaign["id"], character.id,
        ObjectiveTriggerType.TALK_TO_NPC, subject_id=elder.id,
    )
    assert participation("Relato da Primeira Chegada") == QuestStatus.ACTIVE

    evaluate_objective_trigger(
        db_session, campaign["id"], character.id,
        ObjectiveTriggerType.TALK_TO_NPC, subject_id=guildmaster.id,
    )
    assert participation("Relato da Primeira Chegada") == QuestStatus.COMPLETED
    # The board report still requires reading the public board first.
    assert participation("Ronda dos Avisos") == QuestStatus.ACTIVE


def test_npc_naming_a_contract_reveals_it_to_the_player(client, db_session):
    # Audit: a reveal required every capitalized word of the description
    # ("Converse", "Leia"); it is now matched on the quoted title alone.
    from app.ai.context_builder import fact_is_revealed_in_text
    from app.db.models.knowledge import KnowledgeFact
    from app.game.npcs.service import KnownFact

    _started_world(client, db_session)
    quest = db_session.query(Quest).filter(Quest.name == "Relato da Primeira Chegada").one()
    fact = db_session.query(KnowledgeFact).filter(
        KnowledgeFact.fact_key == f"quest:{quest.id}:exists"
    ).one()
    known = KnownFact(subject=fact.subject, fact_key=fact.fact_key, statement=fact.statement,
                      source="", certainty="", discovered_at=None)

    assert '"Relato da Primeira Chegada"' in fact.statement
    assert fact_is_revealed_in_text(
        known, "— Temos o Relato da Primeira Chegada, se quiser ajudar a guilda."
    )
    assert not fact_is_revealed_in_text(known, "— A guilda sempre tem trabalho para quem procura.")
    legacy = KnownFact(subject=fact.subject, fact_key=fact.fact_key,
                       statement="Relato da Primeira Chegada: Converse com o ancião.",
                       source="", certainty="", discovered_at=None)
    assert fact_is_revealed_in_text(legacy, "— Pegue o relato da primeira chegada.")


def test_guildmasters_work_at_their_guilds_during_the_day(client, db_session):
    # Audit: the guildmaster stood in the square and the guild was empty, so
    # "voltar à guilda e entregar" found nobody.
    from app.game.game_state import build_game_state
    from app.game.npcs.service import effective_npc_location_id

    campaign, character = _started_world(client, db_session)
    guildmaster = db_session.query(NPC).filter(
        NPC.role == "mestre da guilda de aventureiros"
    ).one()

    assert effective_npc_location_id(guildmaster) == guildmaster.workplace_location_id
    character.location_id = guildmaster.workplace_location_id
    db_session.flush()
    state = build_game_state(db_session, campaign["id"], character.id)
    assert guildmaster.id in {npc.id for npc in state.nearby_npcs}


def test_actions_expire_notices_past_their_deadline(client, db_session):
    from app.game.time.clock import get_world_time
    from app.api.dependencies.llm import set_llm_service_override

    campaign, character = _started_world(client, db_session)
    notice = db_session.query(Notice).filter(Notice.status == NoticeStatus.ACTIVE).first()
    notice.expires_world_minute = get_world_time(db_session, campaign["id"]).total_minutes() - 1
    db_session.commit()

    set_llm_service_override(PassiveLLM())
    response = client.post(
        f"/api/campaigns/{campaign['id']}/actions",
        params={"character_id": character.id},
        json={"text": "Espero um pouco."},
    )

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(Notice, notice.id).status == NoticeStatus.EXPIRED


def test_asking_for_work_surfaces_the_guildmasters_contracts(client, db_session):
    # Live check: with a title-only fact, "Tem algum trabalho?" shared no word
    # with it, the narrator never saw the contracts and invented others.
    from app.core.enums import KnowerType
    from app.game.npcs.service import relevant_known_facts

    campaign, _character = _started_world(client, db_session)
    guildmaster = db_session.query(NPC).filter(
        NPC.role == "mestre da guilda de aventureiros"
    ).one()

    for question in ("Tem algum trabalho para um recém-chegado?", "A guilda tem algum contrato aberto?"):
        facts = relevant_known_facts(
            db_session, campaign["id"], KnowerType.NPC, guildmaster.id,
            scene_subjects=[], player_input=question,
        )
        titles = {fact.statement for fact in facts if fact.fact_key.startswith("quest:")}
        assert any("Relato da Primeira Chegada" in title for title in titles), question


def test_asking_the_guildmaster_about_work_lets_the_contracts_be_accepted(client, db_session):
    # Live check: the guildmaster described both contracts by content, not
    # title, so they were never registered as known and couldn't be accepted.
    from app.game.quests.discovery import is_quest_known_to_character

    campaign, character = _started_world(client, db_session)
    guildmaster = db_session.query(NPC).filter(
        NPC.role == "mestre da guilda de aventureiros"
    ).one()
    character.location_id = guildmaster.workplace_location_id
    db_session.commit()

    class GuildmasterTalk(LLMService):
        def generate(self, system, prompt):
            if "Ação do jogador" in prompt:
                return json.dumps({"intent": "TALK", "target": guildmaster.name})
            return "— Há dois contratos no quadro. Um é sobre a chegada de vocês."

    llm = GuildmasterTalk()
    engine.resolve_action(
        db_session, llm, campaign["id"], character.id,
        f'"{guildmaster.name}, tem algum trabalho para mim?"', intent_llm_service=llm,
    )

    quests = db_session.query(Quest).filter(Quest.name.in_(
        ("Relato da Primeira Chegada", "Ronda dos Avisos")
    )).all()
    assert quests and all(
        is_quest_known_to_character(db_session, campaign["id"], character.id, quest.id)
        for quest in quests
    )
