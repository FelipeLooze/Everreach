"""Phase 24P — Narrative Observability & Replay.

Mirrors app.game.visual.observability.log_generation_event exactly —
"use current logging/storage conventions" (spec's own words), not a
parallel telemetry system: one structured, greppable log line per
narrative turn, every field name stable across calls, a field that
doesn't apply simply omitted rather than printed as "None".

This is deliberately the SUMMARY line only — the identifying/config/
outcome fields a developer needs to find the right turn at all. The
spec's other named fields (raw output, validation findings, repair
attempts) already have their own appropriately-detailed DEBUG logging
throughout narrator.py/context_builder.py/intent_parser.py; duplicating
full narrative text and violation lists into this one-line-per-turn
summary would make it useless to scan. What ties this summary line to
those existing, richer logs is narrative_request_id — every log record
emitted anywhere during app.game.engine.resolve_action() automatically
carries the same one (app.core.logging's contextvar-based filter, set
once per request), so "why did Aldric say this" is answerable by
grepping that one ID across the whole log, not by reconstructing turns
from timestamps.
"""
import logging

from app.core.logging import get_logger

logger = get_logger("game")

_PLAYER_INPUT_LOG_CHARS = 200
_OUTPUT_LOG_CHARS = 300


def _clip_for_log(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def log_narrative_request(
    *,
    narrative_request_id: str,
    campaign_id: str,
    character_id: str,
    active_npc_id: str | None = None,
    player_input: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    num_predict: int | None = None,
    context_fingerprint: str | None = None,
    context_chars: int | None = None,
    estimated_tokens: int | None = None,
    retrieved_source_ids: list[str] | None = None,
    narration_outcome: str | None = None,
    narrator_unavailable: bool | None = None,
    final_output: str | None = None,
    latency_ms: float | None = None,
) -> None:
    fields = {
        "narrative_request_id": narrative_request_id,
        "campaign_id": campaign_id,
        "character_id": character_id,
        "active_npc_id": active_npc_id,
        "player_input": (
            _clip_for_log(player_input, _PLAYER_INPUT_LOG_CHARS) if player_input else None
        ),
        "model": model,
        "temperature": temperature,
        "num_predict": num_predict,
        "context_fingerprint": context_fingerprint,
        "context_chars": context_chars,
        "estimated_tokens": estimated_tokens,
        "retrieved_source_ids": (
            ",".join(retrieved_source_ids) if retrieved_source_ids else None
        ),
        "narration_outcome": narration_outcome,
        "narrator_unavailable": narrator_unavailable,
        "final_output": (
            _clip_for_log(final_output, _OUTPUT_LOG_CHARS) if final_output else None
        ),
        "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
    }
    rendered = " ".join(
        f"{key}={_render_field(value)}" for key, value in fields.items() if value is not None
    )
    level = logging.WARNING if narrator_unavailable else logging.INFO
    logger.log(level, "narrative_request %s", rendered)


def _render_field(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return repr(str(value))
