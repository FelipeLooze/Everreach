import json
import re
from dataclasses import dataclass
from math import isfinite

from sqlalchemy.orm import Session

from app.core.enums import (
    EventType,
    ProfessionActivityOutcome,
    ProfessionXPSource,
)
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.db.models.profession import CharacterProfession, Profession
from app.game.professions.service import award_profession_xp
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


COMMON_GATHERING_BASE_XP = 0.1
PROFESSION_REPETITION_WINDOW_MINUTES = 24 * 60
_PROFESSION_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_OUTCOME_MULTIPLIERS = {
    ProfessionActivityOutcome.FAILURE: 0.0,
    ProfessionActivityOutcome.PARTIAL: 0.5,
    ProfessionActivityOutcome.SUCCESS: 1.0,
}


@dataclass(frozen=True)
class ProfessionActivityResult:
    source: ProfessionXPSource
    outcome: ProfessionActivityOutcome
    repetition_count: int
    repetition_multiplier: float
    level_relevance_multiplier: float
    profession_xp_before_affinity: float
    progress: CharacterProfession | None


def _current_profession_level(
    db: Session,
    character_id: str,
    profession_key: str,
) -> int:
    row = (
        db.query(CharacterProfession)
        .join(Profession)
        .filter(
            CharacterProfession.character_id == character_id,
            Profession.key == profession_key,
        )
        .first()
    )
    return row.level if row is not None else 0


def _previous_repetitions(
    db: Session,
    campaign_id: str,
    character_id: str,
    profession_key: str,
    source: ProfessionXPSource,
    activity_key: str,
) -> int:
    current_world_minute = get_world_time(
        db,
        campaign_id,
    ).total_minutes()
    events = (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign_id,
            WorldEvent.actor_type == "character",
            WorldEvent.actor_id == character_id,
            WorldEvent.event_type
            == EventType.PLAYER_COMPLETED_PROFESSION_ACTIVITY.value,
            WorldEvent.world_minute
            >= current_world_minute - PROFESSION_REPETITION_WINDOW_MINUTES,
        )
        .all()
    )
    count = 0
    for event in events:
        try:
            payload = json.loads(event.payload_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if (
            payload.get("profession_key") == profession_key
            and payload.get("source") == source.value
            and payload.get("activity_key") == activity_key
        ):
            count += 1
    return count


def award_profession_activity_xp(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    source: ProfessionXPSource,
    profession_key: str,
    profession_name: str,
    activity_key: str,
    base_xp: float,
    task_complexity_level: int,
    outcome: ProfessionActivityOutcome = ProfessionActivityOutcome.SUCCESS,
    learning_quality: float = 1.0,
) -> ProfessionActivityResult:
    """Resolve one real professional learning opportunity and record its factors."""
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    if not isinstance(source, ProfessionXPSource):
        raise ValueError("Invalid Profession XP source.")
    if not isinstance(outcome, ProfessionActivityOutcome):
        raise ValueError("Invalid profession activity outcome.")
    if not isfinite(base_xp) or base_xp <= 0:
        raise ValueError("Profession activity base XP must be finite and positive.")
    if not isfinite(learning_quality) or not 0 <= learning_quality <= 1:
        raise ValueError("Learning quality must be between 0 and 1.")
    if task_complexity_level < 0:
        raise ValueError("Task complexity level cannot be negative.")

    normalized_profession_key = profession_key.strip().upper()
    normalized_profession_name = profession_name.strip()
    normalized_activity_key = activity_key.strip().lower()
    if not _PROFESSION_KEY_PATTERN.fullmatch(normalized_profession_key):
        raise ValueError("Invalid profession key.")
    if not normalized_profession_name:
        raise ValueError("Profession name is required.")
    if not normalized_activity_key:
        raise ValueError("Profession activity key is required.")

    current_level = _current_profession_level(
        db,
        character.id,
        normalized_profession_key,
    )
    repetition_count = _previous_repetitions(
        db,
        campaign_id,
        character.id,
        normalized_profession_key,
        source,
        normalized_activity_key,
    )
    repetition_multiplier = 1.0 / (repetition_count + 1)
    level_gap = max(0, current_level - task_complexity_level)
    level_relevance_multiplier = 1.0 / (level_gap + 1)
    profession_xp = (
        base_xp
        * _OUTCOME_MULTIPLIERS[outcome]
        * learning_quality
        * repetition_multiplier
        * level_relevance_multiplier
    )

    progress = None
    if profession_xp > 0:
        progress = award_profession_xp(
            db,
            campaign_id,
            character,
            profession_key=normalized_profession_key,
            profession_name=normalized_profession_name,
            amount=profession_xp,
        )

    log_event(
        db,
        campaign_id,
        EventType.PLAYER_COMPLETED_PROFESSION_ACTIVITY,
        actor_type="character",
        actor_id=character.id,
        payload={
            "source": source.value,
            "outcome": outcome.value,
            "profession_key": normalized_profession_key,
            "profession_name": normalized_profession_name,
            "activity_key": normalized_activity_key,
            "base_xp": base_xp,
            "learning_quality": learning_quality,
            "task_complexity_level": task_complexity_level,
            "profession_level": current_level,
            "repetition_count": repetition_count,
            "repetition_multiplier": repetition_multiplier,
            "level_relevance_multiplier": level_relevance_multiplier,
            "profession_xp_before_affinity": profession_xp,
        },
    )
    db.flush()
    return ProfessionActivityResult(
        source=source,
        outcome=outcome,
        repetition_count=repetition_count,
        repetition_multiplier=repetition_multiplier,
        level_relevance_multiplier=level_relevance_multiplier,
        profession_xp_before_affinity=profession_xp,
        progress=progress,
    )


def award_gathering_xp(*args, base_xp: float = COMMON_GATHERING_BASE_XP, **kwargs):
    return award_profession_activity_xp(
        *args,
        source=ProfessionXPSource.GATHERING,
        base_xp=base_xp,
        **kwargs,
    )


def award_work_xp(*args, base_xp: float, **kwargs):
    return award_profession_activity_xp(
        *args,
        source=ProfessionXPSource.WORK,
        base_xp=base_xp,
        **kwargs,
    )


def award_crafting_xp(*args, base_xp: float, **kwargs):
    return award_profession_activity_xp(
        *args,
        source=ProfessionXPSource.CRAFTING,
        base_xp=base_xp,
        **kwargs,
    )


def award_practice_xp(*args, base_xp: float, **kwargs):
    return award_profession_activity_xp(
        *args,
        source=ProfessionXPSource.PRACTICE,
        base_xp=base_xp,
        **kwargs,
    )
