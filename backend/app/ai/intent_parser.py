import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from app.ai.llm_call import call_llm
from app.ai.llm_service import (
    LLMEmptyCompletionError,
    LLMRateLimitError,
    LLMService,
    LLMServiceError,
    LLMTimeoutError,
)
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
    pattern_key: str | None = None
    domains: str | None = None
    technique_type: str | None = None
    # "P2": who the player means, from the numbered PESSOAS PRESENTES list
    # (app.ai.people_present). None when nobody or ambiguous.
    person_ref: str | None = None


# Each intent call sends ~4k prompt tokens and Groq's free tier allows 8k
# tokens per minute, so back-to-back turns routinely hit a 429 with a wait
# of a few seconds; Groq also occasionally returns an empty completion.
# Either one used to drop the turn straight to FREEFORM (confirmed in
# playtest). One retry is cheap for a classification call; a long wait is
# not worth stalling the turn for.
_MAX_RATE_LIMIT_WAIT_SECONDS = 8.0


def _call_with_one_retry(llm_service: LLMService, prompt: str) -> str:
    try:
        return call_llm(llm_service, _SYSTEM_PROMPT, prompt, purpose="INTENT")
    except LLMRateLimitError as exc:
        wait = exc.retry_after_seconds
        if wait is None or wait > _MAX_RATE_LIMIT_WAIT_SECONDS:
            raise
        logger.info("intent parser: rate limited, retrying in %.1fs", wait)
        time.sleep(wait + 0.25)
    except LLMEmptyCompletionError:
        logger.info("intent parser: empty completion, retrying once")
    except LLMTimeoutError:
        raise
    except LLMServiceError as exc:
        # Free NVIDIA answers an occasional 500 that clears within a second;
        # one more try is far cheaper than losing the turn's mechanics.
        logger.info("intent parser: provider error (%s), retrying once", exc)
    return call_llm(llm_service, _SYSTEM_PROMPT, prompt, purpose="INTENT", attempt=2)


def parse(llm_service: LLMService, text: str, context: str) -> Intent:
    """Ask the LLM to classify player intent. This NEVER decides game outcomes —
    it only produces a structured hint the Game Engine may use. If the LLM is
    unreachable or returns something unparseable, we fall back to FREEFORM so the
    action still gets narrated instead of failing the whole request."""
    prompt = f"Contexto do mundo:\n{context}\n\nAção do jogador:\n{text}"
    logger.debug("INTENT PARSER PROMPT\n%s", prompt)

    try:
        raw = _call_with_one_retry(llm_service, prompt)
    except LLMServiceError:
        logger.info("intent parser: LLM unavailable, falling back to FREEFORM")
        return Intent(type=ActionIntentType.FREEFORM, target=None, raw_text=text)

    logger.debug("INTENT PARSER RAW RESPONSE\n%s", raw)

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
        pattern_key,
        domains,
        technique_type,
    ) = _decode_response(raw)
    return Intent(
        type=intent_type,
        target=target,
        raw_text=text,
        person_ref=_person_ref(raw),
        pace=pace,
        secondary_target=secondary_target,
        slot=slot,
        weapon=weapon,
        attack_type=attack_type,
        damage_profile=damage_profile,
        body_area=body_area,
        pattern_key=pattern_key,
        domains=domains,
        technique_type=technique_type,
    )


def _parse_response(
    raw: str,
) -> tuple[ActionIntentType, str | None, TravelPace]:
    intent_type, target, pace, *_details = _decode_response(raw)
    return intent_type, target, pace


def _person_ref(raw: str) -> str | None:
    match = re.search(r'"person"\s*:\s*"(P\d{1,2})"', raw or "", re.IGNORECASE)
    return match.group(1).upper() if match else None


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
    str | None,
    str | None,
    str | None,
]:
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        partial = _decode_partial_response(raw)
        if partial is not None:
            logger.warning(
                "intent parser: salvaged intent from truncated LLM response: %r",
                raw,
            )
            return partial
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
        _optional_text(data.get("pattern_key")),
        _optional_text(data.get("domains")),
        _optional_text(data.get("technique_type")),
    )


def _decode_partial_response(raw: str):
    """Recover only explicit leading fields from a truncated JSON object.

    This never guesses an intent: it accepts the same enum value the model
    already emitted before its response was cut off. Missing optional fields
    remain unset and movement pace stays conservative.
    """
    intent_match = re.search(r'"intent"\s*:\s*"([A-Z_]+)"', raw, re.IGNORECASE)
    if intent_match is None:
        return None
    intent_value = intent_match.group(1).upper()
    if intent_value not in _VALID_INTENTS:
        return None

    target = None
    target_match = re.search(r'"target"\s*:\s*(null|"([^"\\]*(?:\\.[^"\\]*)*)")', raw)
    if target_match is not None and target_match.group(1) != "null":
        try:
            target = _optional_text(json.loads(target_match.group(1)))
        except json.JSONDecodeError:
            target = None

    pace = TravelPace.NORMAL
    pace_match = re.search(r'"pace"\s*:\s*"([A-Z_]+)"', raw, re.IGNORECASE)
    if pace_match is not None:
        try:
            pace = TravelPace(pace_match.group(1).upper())
        except ValueError:
            pass

    return (
        ActionIntentType(intent_value),
        target,
        pace,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def _optional_text(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
