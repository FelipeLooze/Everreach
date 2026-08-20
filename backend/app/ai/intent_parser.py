import json
from dataclasses import dataclass
from pathlib import Path

from app.ai.llm_service import LLMService, LLMServiceError
from app.core.enums import ActionIntentType, TravelPace
from app.core.logging import get_logger

logger = get_logger("context")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "intent_parser_system.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_VALID_INTENTS = {t.value for t in ActionIntentType}


@dataclass
class Intent:
    type: ActionIntentType
    target: str | None
    raw_text: str
    pace: TravelPace = TravelPace.NORMAL
    secondary_target: str | None = None
    slot: str | None = None
    weapon: str | None = None
    attack_type: str | None = None
    damage_profile: str | None = None
    body_area: str | None = None


def parse(llm_service: LLMService, text: str, context: str) -> Intent:
    """Ask the LLM to classify player intent. This NEVER decides game outcomes —
    it only produces a structured hint the Game Engine may use. If the LLM is
    unreachable or returns something unparseable, we fall back to FREEFORM so the
    action still gets narrated instead of failing the whole request."""
    prompt = f"Contexto do mundo:\n{context}\n\nAção do jogador:\n{text}"

    try:
        raw = llm_service.generate(_SYSTEM_PROMPT, prompt)
    except LLMServiceError:
        logger.info("intent parser: LLM unavailable, falling back to FREEFORM")
        return Intent(type=ActionIntentType.FREEFORM, target=None, raw_text=text)

    (
        intent_type,
        target,
        pace,
        secondary_target,
        slot,
        weapon,
        attack_type,
        damage_profile,
        body_area,
    ) = _decode_response(raw)
    return Intent(
        type=intent_type,
        target=target,
        raw_text=text,
        pace=pace,
        secondary_target=secondary_target,
        slot=slot,
        weapon=weapon,
        attack_type=attack_type,
        damage_profile=damage_profile,
        body_area=body_area,
    )


def _parse_response(
    raw: str,
) -> tuple[ActionIntentType, str | None, TravelPace]:
    intent_type, target, pace, *_details = _decode_response(raw)
    return intent_type, target, pace


def _decode_response(
    raw: str,
) -> tuple[
    ActionIntentType,
    str | None,
    TravelPace,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning(
            "intent parser: could not parse LLM response: %r",
            raw,
        )
        return (
            ActionIntentType.FREEFORM,
            None,
            TravelPace.NORMAL,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    intent_str = str(
        data.get("intent", "")
    ).upper()

    target = _optional_text(data.get("target"))

    if intent_str not in _VALID_INTENTS:
        return (
            ActionIntentType.FREEFORM,
            target,
            TravelPace.NORMAL,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    pace_str = str(
        data.get("pace", TravelPace.NORMAL.value)
    ).upper()

    try:
        pace = TravelPace(pace_str)
    except ValueError:
        pace = TravelPace.NORMAL

    return (
        ActionIntentType(intent_str),
        target,
        pace,
        _optional_text(data.get("secondary_target")),
        _optional_text(data.get("slot")),
        _optional_text(data.get("weapon")),
        _optional_text(data.get("attack_type")),
        _optional_text(data.get("damage_profile")),
        _optional_text(data.get("body_area")),
    )


def _optional_text(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
