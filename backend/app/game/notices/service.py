"""Phase 12I — Quest / Notice Boards.

BOARDS ARE NOT QUEST GENERATORS: reading a board never creates a Notice —
post_notice is the only way one comes to exist, and it always requires
real context (a category, text, and usually an author or a linked Quest)
supplied by the caller. Not every settlement has a board — the board
itself is just an ordinary LocationFeature (Phase 4); nothing marks one
as "a board" other than Notices actually pointing at it via
board_feature_id.

A Notice is more than a Quest pointer — most NoticeCategory values (JOB,
TRADE, WARNING, LOST_PROPERTY, RUMOR...) never carry a quest_id at all;
they are just world information a character can read, exactly like the
spec's Cardal board example ("east bridge closed" needs no Quest).
"""

from sqlalchemy.orm import Session

from app.core.enums import EventType, NoticeCategory, NoticeStatus
from app.db.models.character import Character
from app.db.models.location import LocationFeature
from app.db.models.notice import Notice
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


class NoticeBoardError(Exception):
    pass


def post_notice(
    db: Session,
    campaign_id: str,
    board_feature_id: str,
    *,
    category: NoticeCategory,
    title: str,
    text: str,
    author_npc_id: str | None = None,
    quest_id: str | None = None,
    expires_world_minute: int | None = None,
) -> Notice:
    board = db.get(LocationFeature, board_feature_id)
    if board is None:
        raise NoticeBoardError(f"Quadro de avisos desconhecido: {board_feature_id}")

    notice = Notice(
        campaign_id=campaign_id,
        board_feature_id=board_feature_id,
        category=category,
        title=title,
        text=text,
        author_npc_id=author_npc_id,
        quest_id=quest_id,
        posted_world_minute=get_world_time(db, campaign_id).total_minutes(),
        expires_world_minute=expires_world_minute,
    )
    db.add(notice)
    db.flush()
    log_event(
        db,
        campaign_id,
        EventType.NOTICE_POSTED,
        actor_type="npc" if author_npc_id else "world",
        actor_id=author_npc_id or "",
        payload={"notice_id": notice.id, "board_feature_id": board_feature_id, "category": category},
    )
    return notice


def read_notice_board(db: Session, character_id: str, board_feature_id: str) -> list[Notice]:
    """PHYSICAL PRESENCE (Phase 12I): the character must actually be at the
    board's location. Returns only ACTIVE notices — a claimed, completed,
    expired or withdrawn posting is history, not currently on the board."""
    character = db.get(Character, character_id)
    if character is None:
        raise NoticeBoardError(f"Personagem desconhecido: {character_id}")
    board = db.get(LocationFeature, board_feature_id)
    if board is None:
        raise NoticeBoardError(f"Quadro de avisos desconhecido: {board_feature_id}")
    if character.location_id != board.location_id:
        raise NoticeBoardError(
            f"{character.name} não está no mesmo local que esse quadro de avisos."
        )

    return (
        db.query(Notice)
        .filter(Notice.board_feature_id == board_feature_id, Notice.status == NoticeStatus.ACTIVE)
        .order_by(Notice.posted_world_minute.desc())
        .all()
    )


def withdraw_notice(db: Session, campaign_id: str, notice_id: str, *, reason: str = "") -> Notice:
    """The requester/author withdraws a still-open posting."""
    notice = db.get(Notice, notice_id)
    if notice is None:
        raise NoticeBoardError(f"Aviso desconhecido: {notice_id}")
    if notice.status not in (NoticeStatus.ACTIVE, NoticeStatus.CLAIMED):
        raise NoticeBoardError(f"Não é possível retirar um aviso com status {notice.status}.")
    notice.status = NoticeStatus.WITHDRAWN
    db.flush()
    log_event(
        db,
        campaign_id,
        EventType.NOTICE_WITHDRAWN,
        actor_type="world",
        payload={"notice_id": notice_id, "reason": reason},
    )
    return notice


def expire_notices(db: Session, campaign_id: str) -> list[Notice]:
    """Call whenever world time advances (mirrors
    app.game.quests.service.check_deadlines) — a posting does not stay on
    the board forever just because nobody read it."""
    now = get_world_time(db, campaign_id).total_minutes()
    expiring = (
        db.query(Notice)
        .filter(
            Notice.campaign_id == campaign_id,
            Notice.status == NoticeStatus.ACTIVE,
            Notice.expires_world_minute.isnot(None),
            Notice.expires_world_minute <= now,
        )
        .all()
    )
    for notice in expiring:
        notice.status = NoticeStatus.EXPIRED
        log_event(
            db,
            campaign_id,
            EventType.NOTICE_EXPIRED,
            actor_type="world",
            payload={"notice_id": notice.id},
        )
    if expiring:
        db.flush()
    return expiring


_QUEST_STATUS_TO_NOTICE_STATUS = {
    "COMPLETED": NoticeStatus.COMPLETED,
    "RESOLVED_EXTERNALLY": NoticeStatus.OUTDATED,
    "CANCELLED": NoticeStatus.WITHDRAWN,
    "EXPIRED": NoticeStatus.EXPIRED,
}


def sync_notice_with_linked_quest(db: Session, campaign_id: str, notice_id: str) -> Notice:
    """BOARD EVOLUTION (Phase 12I): a posting linked to a Quest should
    reflect that Quest's real resolution — completed, resolved by someone
    else, withdrawn, expired — rather than staying frozen once the
    situation it described has moved on. Not automatically called
    anywhere yet (no content today links a Notice's quest_id to an
    already-resolving Quest to observe this against); it's the ready
    primitive for whichever caller needs it."""
    from app.db.models.quest import Quest

    notice = db.get(Notice, notice_id)
    if notice is None:
        raise NoticeBoardError(f"Aviso desconhecido: {notice_id}")
    if notice.quest_id is None:
        return notice
    if notice.status not in (NoticeStatus.ACTIVE, NoticeStatus.CLAIMED):
        return notice

    quest = db.get(Quest, notice.quest_id)
    if quest is None:
        return notice
    new_status = _QUEST_STATUS_TO_NOTICE_STATUS.get(quest.status)
    if new_status is None or new_status == notice.status:
        return notice

    notice.status = new_status
    db.flush()
    log_event(
        db,
        campaign_id,
        EventType.NOTICE_UPDATED,
        actor_type="world",
        payload={"notice_id": notice.id, "quest_id": quest.id, "new_status": new_status},
    )
    return notice
