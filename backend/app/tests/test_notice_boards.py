"""Phase 12I — Quest / Notice Boards.

A board is just an ordinary LocationFeature — nothing marks it as special
until a Notice actually points at it. Reading a board never creates
anything; posting always requires real, explicit context. Physical
presence is required to read, and a posting evolves (or disappears) as
the situation it describes changes.
"""

from app.core.enums import NoticeCategory, NoticeStatus, QuestSource
from app.db.models.location import Location, LocationFeature
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.notices.service import (
    NoticeBoardError,
    expire_notices,
    post_notice,
    read_notice_board,
    sync_notice_with_linked_quest,
    withdraw_notice,
)
from app.game.quests.service import create_quest, resolve_quest_externally
from app.game.time.clock import advance_world_time, get_world_time
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Notice Boards")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    board = LocationFeature(location_id=village.id, name="Quadro de Avisos de Cardal")
    db_session.add(board)
    db_session.flush()
    return campaign, region, village, character, board


def test_post_notice_requires_real_context(db_session):
    campaign, region, village, character, board = _setup(db_session)
    osgar = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()

    notice = post_notice(
        db_session,
        campaign.id,
        board.id,
        category=NoticeCategory.MISSING_PERSON,
        title="Cabras desaparecidas",
        text="Três cabras sumiram ao norte de Cardal.",
        author_npc_id=osgar.id,
    )

    assert notice.status == NoticeStatus.ACTIVE
    assert notice.author_npc_id == osgar.id
    assert notice.posted_world_minute == get_world_time(db_session, campaign.id).total_minutes()


def test_reading_a_board_never_creates_a_notice(db_session):
    campaign, region, village, character, board = _setup(db_session)

    notices = read_notice_board(db_session, character.id, board.id)

    assert notices == []


def test_reading_a_board_requires_physical_presence(db_session):
    campaign, region, village, character, board = _setup(db_session)
    far_location = db_session.query(Location).filter(Location.id != village.id).first()
    other_board = LocationFeature(location_id=far_location.id, name="Quadro Distante")
    db_session.add(other_board)
    db_session.flush()

    try:
        read_notice_board(db_session, character.id, other_board.id)
        assert False, "expected NoticeBoardError"
    except NoticeBoardError:
        pass


def test_read_notice_board_only_returns_active_notices(db_session):
    campaign, region, village, character, board = _setup(db_session)
    active = post_notice(
        db_session, campaign.id, board.id,
        category=NoticeCategory.WARNING, title="Ponte fechada", text="A ponte leste está fechada.",
    )
    withdrawn = post_notice(
        db_session, campaign.id, board.id,
        category=NoticeCategory.TRADE, title="Compro peles", text="Peles de lobo, bom preço.",
    )
    withdraw_notice(db_session, campaign.id, withdrawn.id)

    notices = read_notice_board(db_session, character.id, board.id)

    assert [n.id for n in notices] == [active.id]


def test_expire_notices_only_affects_past_deadlines(db_session):
    campaign, region, village, character, board = _setup(db_session)
    now = get_world_time(db_session, campaign.id).total_minutes()
    soon = post_notice(
        db_session, campaign.id, board.id,
        category=NoticeCategory.TRAVEL, title="Caravana", text="Caravana parte em breve.",
        expires_world_minute=now + 30,
    )
    forever = post_notice(
        db_session, campaign.id, board.id,
        category=NoticeCategory.ANNOUNCEMENT, title="Festival", text="Festival anual em Cardal.",
    )

    advance_world_time(db_session, campaign.id, 60)
    expired = expire_notices(db_session, campaign.id)

    assert [n.id for n in expired] == [soon.id]
    assert db_session.get(type(soon), soon.id).status == NoticeStatus.EXPIRED
    assert db_session.get(type(forever), forever.id).status == NoticeStatus.ACTIVE


def test_sync_notice_with_linked_quest_reflects_external_resolution(db_session):
    campaign, region, village, character, board = _setup(db_session)
    quest = create_quest(db_session, region.id, "Cabras desaparecidas", source=QuestSource.NPC_REQUEST)
    notice = post_notice(
        db_session, campaign.id, board.id,
        category=NoticeCategory.QUEST_REQUEST, title="Cabras desaparecidas",
        text="Três cabras sumiram.", quest_id=quest.id,
    )

    resolve_quest_externally(db_session, campaign.id, quest.id, note="Outro viajante resolveu.")
    updated = sync_notice_with_linked_quest(db_session, campaign.id, notice.id)

    assert updated.status == NoticeStatus.OUTDATED


def test_withdrawing_an_already_withdrawn_notice_raises(db_session):
    campaign, region, village, character, board = _setup(db_session)
    notice = post_notice(
        db_session, campaign.id, board.id,
        category=NoticeCategory.RUMOR, title="Boato", text="Dizem que...",
    )
    withdraw_notice(db_session, campaign.id, notice.id)

    try:
        withdraw_notice(db_session, campaign.id, notice.id)
        assert False, "expected NoticeBoardError"
    except NoticeBoardError:
        pass
