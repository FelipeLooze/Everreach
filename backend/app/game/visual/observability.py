"""Phase 23D-P — Observability & Debugging.

One structured log line per orchestration transition, all rendered by
log_generation_event so every field name stays consistent across the
whole pipeline rather than a different ad hoc message shape per call
site. Every field the spec names is supported here: generation_
request_id, campaign_id, entity_type, entity_id, asset_type, workflow
(_version), prompt_id, duration, status, failure reason (error_code/
error_message), asset_id. A field that does not apply to a given event
is simply omitted from the rendered line rather than printed as "None".
"""
import logging

from app.core.logging import get_logger

logger = get_logger("visual")


def log_generation_event(
    event: str,
    *,
    request_id: str | None = None,
    campaign_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    asset_type: str | None = None,
    workflow_key: str | None = None,
    workflow_version: str | None = None,
    prompt_id: str | None = None,
    duration_seconds: float | None = None,
    status: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    asset_id: str | None = None,
) -> None:
    fields = {
        "generation_request_id": request_id,
        "campaign_id": campaign_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "asset_type": asset_type,
        "workflow": workflow_key,
        "workflow_version": workflow_version,
        "prompt_id": prompt_id,
        "duration_seconds": round(duration_seconds, 3) if duration_seconds is not None else None,
        "status": status,
        "error_code": error_code,
        "error_message": error_message,
        "asset_id": asset_id,
    }
    rendered = " ".join(
        f"{key}={_render_field(value)}" for key, value in fields.items() if value is not None
    )
    level = logging.WARNING if error_code else logging.INFO
    logger.log(level, "visual_generation event=%s %s", event, rendered)


def _render_field(value) -> str:
    """Numbers render bare (duration_seconds=1.235); everything else —
    including a VisualGenerationErrorCode/Status StrEnum member —
    renders as its plain string value, quoted (str() first, so a
    StrEnum never shows Python's <ClassName.MEMBER: 'value'> repr)."""
    if isinstance(value, (int, float)):
        return str(value)
    return repr(str(value))
