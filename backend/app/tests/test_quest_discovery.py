"""Phase 12J — Quest Discovery & Knowledge.

Quest exists != character knows quest exists. create_quest registers the
existence as a Knowledge fact (a world truth, Phase 4/5) but teaches it
to nobody. Discovery only happens through a real, specific source —
reading a linked notice (CONFIRMED) or an NPC telling the character
(BELIEVED by default, since it's the NPC's belief, not automatic truth).
"""

from app.core.enums import KnowledgeCertainty, NoticeCategory, QuestSource
from app.db.models.knowledge import KnowledgeFact
from app.db.models.location import LocationFeature
from app.game.character.service import create_character
from app.game.notices.service import post_notice, read_notice_board
from app.game.quests.discovery import (
    is_quest_known_to_character,
    learn_about_quest_from_npc,
)
from app.game.quests.service import create_quest
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Quest Discovery")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, village, character


def test_creating_a_quest_does_not_teach_it_to_anyone(db_session):
    campaign, region, village, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Cabras desaparecidas", source=QuestSource.NPC_REQUEST)

    assert is_quest_known_to_character(db_session, campaign.id, character.id, quest.id) is False


def test_creating_a_quest_registers_its_existence_as_a_knowledge_fact(db_session):
    campaign, region, village, character = _setup(db_session)
    quest = create_quest(
        db_session, region.id, "Cabras desaparecidas",
        "Três cabras sumiram ao norte de Cardal.", source=QuestSource.NPC_REQUEST,
    )

    fact = (
        db_session.query(KnowledgeFact)
        .filter(KnowledgeFact.campaign_id == campaign.id, KnowledgeFact.subject == f"quest:{quest.id}")
        .first()
    )
    assert fact is not None
    assert "Três cabras sumiram" in fact.statement


def test_reading_a_linked_notice_teaches_the_quest_with_confirmed_certainty(db_session):
    campaign, region, village, character = _setup(db_session)
    board = LocationFeature(location_id=village.id, name="Quadro de Avisos de Cardal")
    db_session.add(board)
    db_session.flush()
    quest = create_quest(db_session, region.id, "Cabras desaparecidas", source=QuestSource.NPC_REQUEST)
    post_notice(
        db_session, campaign.id, board.id,
        category=NoticeCategory.QUEST_REQUEST, title="Cabras desaparecidas",
        text="Três cabras sumiram.", quest_id=quest.id,
    )

    assert is_quest_known_to_character(db_session, campaign.id, character.id, quest.id) is False
    read_notice_board(db_session, character.id, board.id)

    assert is_quest_known_to_character(db_session, campaign.id, character.id, quest.id) is True


def test_reading_an_unrelated_notice_teaches_nothing(db_session):
    campaign, region, village, character = _setup(db_session)
    board = LocationFeature(location_id=village.id, name="Quadro de Avisos de Cardal")
    db_session.add(board)
    db_session.flush()
    quest = create_quest(db_session, region.id, "Cabras desaparecidas", source=QuestSource.NPC_REQUEST)
    post_notice(
        db_session, campaign.id, board.id,
        category=NoticeCategory.WARNING, title="Ponte fechada", text="A ponte leste está fechada.",
    )

    read_notice_board(db_session, character.id, board.id)

    assert is_quest_known_to_character(db_session, campaign.id, character.id, quest.id) is False


def test_learning_from_an_npc_defaults_to_believed_not_confirmed(db_session):
    campaign, region, village, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Cabras desaparecidas", source=QuestSource.NPC_REQUEST)

    learn_about_quest_from_npc(db_session, campaign.id, character.id, quest.id)

    fact = (
        db_session.query(KnowledgeFact)
        .filter(KnowledgeFact.campaign_id == campaign.id, KnowledgeFact.subject == f"quest:{quest.id}")
        .first()
    )
    from app.core.enums import KnowerType
    from app.db.models.knowledge import KnowledgeKnower

    knower = (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type == KnowerType.PLAYER,
            KnowledgeKnower.knower_id == character.id,
        )
        .first()
    )
    assert knower.certainty == KnowledgeCertainty.BELIEVED
    assert is_quest_known_to_character(db_session, campaign.id, character.id, quest.id) is True


def test_learning_from_an_npc_can_be_confirmed_when_the_caller_says_so(db_session):
    campaign, region, village, character = _setup(db_session)
    quest = create_quest(db_session, region.id, "Cabras desaparecidas", source=QuestSource.NPC_REQUEST)

    learn_about_quest_from_npc(
        db_session, campaign.id, character.id, quest.id, certainty=KnowledgeCertainty.CONFIRMED
    )

    assert is_quest_known_to_character(db_session, campaign.id, character.id, quest.id) is True
