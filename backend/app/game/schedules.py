"""When a job or a contract happens, and how the player comes to know it.

A job's shift hours are mechanical: a shift must fit inside them. A
contract's schedule is informational, in the giver's words. Either is known
to the player only if the posted notice states it, if the employer said it
when hiring, or once someone who knows it is asked ("quando?", "que
horas?"). Until then the panel and the narrator say "desconhecido" —
playtest: hired with no schedule anywhere, the blacksmith improvised
"começa amanhã, ao nascer do sol" while a shift could be worked right away.
"""

import re
import unicodedata

from sqlalchemy.orm import Session

from app.core.enums import KnowerType, KnowledgeCertainty
from app.db.models.job import Job
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.db.models.quest import Quest
from app.game.npcs.service import knows, teach_fact
from app.game.world.local_knowledge import _ensure_fact

_HOUR_WORDS = (
    "zero", "uma", "duas", "tres", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
    "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete", "dezoito",
    "dezenove", "vinte", "vinte e uma", "vinte e duas", "vinte e tres",
)
_SCHEDULE_QUESTION_PATTERN = re.compile(
    r"\bquando\b|\bque horas?\b|\bhorarios?\b|\ba partir de que\b|\bate que horas\b|\bque dia\b"
)


def _normalized(text: str | None) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", (text or "").casefold())
        if not unicodedata.combining(char)
    )


def is_schedule_question(text: str) -> bool:
    return _SCHEDULE_QUESTION_PATTERN.search(_normalized(text)) is not None


def job_schedule_fact_key(job: Job) -> str:
    return f"job:{job.id}:schedule"


def quest_schedule_fact_key(quest: Quest) -> str:
    return f"quest:{quest.id}:schedule"


def job_hours_text(job: Job) -> str | None:
    if job.shift_start_hour is None or job.shift_end_hour is None:
        return None
    return f"das {job.shift_start_hour}h às {job.shift_end_hour}h"


def ensure_job_schedule(db: Session, campaign_id: str, job: Job, employer_npc) -> None:
    """The schedule fact, known by whoever runs the job."""
    hours = job_hours_text(job)
    if hours is None:
        return
    fact = _ensure_fact(
        db, campaign_id,
        fact_key=job_schedule_fact_key(job),
        subject=f"job:{job.id}",
        statement=f'Os turnos de "{job.title}" são {hours}; um turno pode começar a qualquer momento nesse horário.',
    )
    if employer_npc is not None:
        teach_fact(db, campaign_id, fact.fact_key, KnowerType.NPC, employer_npc.id,
                   source="empregador", certainty=KnowledgeCertainty.CONFIRMED)


def ensure_quest_schedule(db: Session, campaign_id: str, quest: Quest, informed_npcs) -> None:
    if not quest.schedule_text:
        return
    fact = _ensure_fact(
        db, campaign_id,
        fact_key=quest_schedule_fact_key(quest),
        subject=f"quest:{quest.id}",
        statement=f'O contrato "{quest.name}" pode ser feito {quest.schedule_text}.',
    )
    for npc in informed_npcs:
        teach_fact(db, campaign_id, fact.fact_key, KnowerType.NPC, npc.id,
                   source="contratante", certainty=KnowledgeCertainty.CONFIRMED)


def teach_schedule(db: Session, campaign_id: str, character_id: str, fact_key: str, source: str) -> None:
    if db.query(KnowledgeFact).filter(
        KnowledgeFact.campaign_id == campaign_id, KnowledgeFact.fact_key == fact_key
    ).first() is None:
        return
    teach_fact(db, campaign_id, fact_key, KnowerType.PLAYER, character_id,
               source=source, certainty=KnowledgeCertainty.CONFIRMED)


def player_knows_job_schedule(db: Session, campaign_id: str, character_id: str, job: Job) -> bool:
    return knows(db, KnowerType.PLAYER, character_id, job_schedule_fact_key(job), campaign_id)


def player_knows_quest_schedule(db: Session, campaign_id: str, character_id: str, quest: Quest) -> bool:
    return knows(db, KnowerType.PLAYER, character_id, quest_schedule_fact_key(quest), campaign_id)


def shift_refusal(job: Job, world_minute: int) -> str | None:
    """Why a shift cannot start now, or None when it can."""
    if job.shift_start_hour is None or job.shift_end_hour is None:
        return None
    minute_of_day = world_minute % (24 * 60)
    opens, closes = job.shift_start_hour * 60, job.shift_end_hour * 60
    latest_start = closes - job.work_minutes
    if opens <= minute_of_day <= latest_start:
        return None
    hours, minutes = divmod(latest_start, 60)
    latest = f"{hours}h{minutes:02d}" if minutes else f"{hours}h"
    now_hours, now_minutes = divmod(minute_of_day, 60)
    return (
        f"Os turnos de '{job.title}' são {job_hours_text(job)} e um turno precisa começar até "
        f"as {latest}; agora são {now_hours}h{now_minutes:02d}."
    )


# --- Telling schedules in conversation -------------------------------------


def _schedules_known_by(db: Session, campaign_id: str, npc_id: str) -> list[KnowledgeFact]:
    return (
        db.query(KnowledgeFact)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeFact.fact_key.like("%:schedule"),
            KnowledgeKnower.knower_type == KnowerType.NPC.value,
            KnowledgeKnower.knower_id == npc_id,
        )
        .order_by(KnowledgeFact.fact_key)
        .all()
    )


def schedules_npc_can_tell(db: Session, campaign_id: str, npc_id: str, player_input: str) -> list[KnowledgeFact]:
    """Asked "when?", the NPC tells the schedules they know — the ones whose
    job or contract the player named, or all of them when none is named."""
    if not is_schedule_question(player_input):
        return []
    facts = _schedules_known_by(db, campaign_id, npc_id)
    text = _normalized(player_input)
    named = [
        fact for fact in facts
        if (title := re.search(r'"([^"]+)"', fact.statement)) and _title_words_named(title.group(1), text)
    ]
    return named or facts


def _title_words_named(title: str, text: str) -> bool:
    words = [word for word in re.findall(r"\w+", _normalized(title)) if len(word) > 3]
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def _schedule_is_stated(statement: str, narrated_text: str) -> bool:
    text = _normalized(narrated_text)
    hours = re.findall(r"\b(\d{1,2})h\b", statement)
    if hours:
        return all(
            re.search(rf"\b{hour}\s*h|\b{hour}\s*horas|\b{_HOUR_WORDS[int(hour)]}\b", text)
            for hour in hours
        )
    when = re.search(r"pode ser feito (.+?)\.?$", statement)
    if not when:
        return False
    # The giver's own words vary ("a qualquer hora" for "a qualquer hora do
    # dia"): every meaningful word said is enough, the exact phrase is not.
    words = [word for word in re.findall(r"\w+", _normalized(when.group(1))) if len(word) > 3]
    return bool(words) and all(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def tell_schedules(
    db: Session, campaign_id: str, character_id: str, npc, player_input: str, narrated_text: str
) -> str:
    """The schedule the NPC was asked about is said — added as one closing
    line when the narration left it out — and only then learned."""
    for fact in schedules_npc_can_tell(db, campaign_id, npc.id, player_input):
        if not _schedule_is_stated(fact.statement, narrated_text):
            narrated_text = f"{narrated_text.rstrip()}\n\n— {fact.statement} — explica {npc.name}."
        teach_schedule(db, campaign_id, character_id, fact.fact_key, source=f"revelado por {npc.name}")
    return narrated_text
