"""Phase 23D-P — Observability & Debugging.

Attaches a plain logging.Handler directly to the "visual" logger
rather than relying on pytest's caplog: app.core.logging.
configure_logging sets the "everreach" ancestor logger's
propagate=False as soon as anything in the suite triggers app startup
(e.g. the `client` fixture), so caplog silently sees nothing once that
has happened anywhere earlier in the same test process (see
app/tests/test_narrative_trace.py for the same, already-diagnosed
issue). Also resets logging.Logger.manager.disable and the logger's
own level/disabled/handlers around each test, since those are
process-global state a full-suite run must not assume is at its
default.
"""
import logging

from app.core.config import Settings
from app.core.logging import get_logger
from app.game.visual.comfyui_client import ComfyUIClient
from app.game.visual.observability import log_generation_event
from app.game.visual.service import request_visual_asset
from app.game.world.seed import create_campaign


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    @property
    def messages(self) -> list[str]:
        return [record.getMessage() for record in self.records]


def _capture_visual_logs():
    """Returns (handler, teardown_callable). Caller must call
    teardown() in a finally block."""
    logger = get_logger("visual")
    handler = _RecordingHandler()
    original_level = logger.level
    original_disabled = logger.disabled
    original_disable = logging.Logger.manager.disable
    logging.disable(logging.NOTSET)
    logger.disabled = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    def teardown():
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        logger.disabled = original_disabled
        logging.disable(original_disable)

    return handler, teardown


def test_log_generation_event_renders_every_provided_field():
    handler, teardown = _capture_visual_logs()
    try:
        log_generation_event(
            "completed",
            request_id="vgen_1",
            campaign_id="campaign_1",
            entity_type="npc",
            entity_id="npc_mira",
            asset_type="NPC_PORTRAIT",
            workflow_key="EVERREACH_NPC_PORTRAIT",
            workflow_version="V1",
            prompt_id="prompt_1",
            duration_seconds=1.23456,
            status="COMPLETED",
            asset_id="vasset_1",
        )
    finally:
        teardown()

    message = handler.messages[0]
    assert "event=completed" in message
    assert "generation_request_id='vgen_1'" in message
    assert "campaign_id='campaign_1'" in message
    assert "entity_type='npc'" in message
    assert "entity_id='npc_mira'" in message
    assert "asset_type='NPC_PORTRAIT'" in message
    assert "workflow='EVERREACH_NPC_PORTRAIT'" in message
    assert "workflow_version='V1'" in message
    assert "prompt_id='prompt_1'" in message
    assert "duration_seconds=1.235" in message
    assert "status='COMPLETED'" in message
    assert "asset_id='vasset_1'" in message


def test_log_generation_event_omits_fields_that_were_not_given():
    handler, teardown = _capture_visual_logs()
    try:
        log_generation_event("request_created", request_id="vgen_1", status="PENDING")
    finally:
        teardown()

    message = handler.messages[0]
    assert "asset_id=" not in message
    assert "prompt_id=" not in message
    assert "error_code=" not in message


def test_log_generation_event_uses_warning_level_when_error_code_is_present():
    handler, teardown = _capture_visual_logs()
    try:
        log_generation_event("failed", request_id="vgen_1", error_code="COMFYUI_OFFLINE")
    finally:
        teardown()

    assert handler.records[0].levelno == logging.WARNING


def test_log_generation_event_defaults_to_info_level_without_an_error():
    handler, teardown = _capture_visual_logs()
    try:
        log_generation_event("request_created", request_id="vgen_1", status="PENDING")
    finally:
        teardown()

    assert handler.records[0].levelno == logging.INFO


class _AlwaysOfflineClient(ComfyUIClient):
    def is_available(self) -> bool:
        return False

    def system_stats(self) -> dict:
        return {}

    def submit_workflow(self, graph, client_id):
        raise AssertionError

    def get_queue(self) -> dict:
        return {}

    def get_history(self, prompt_id):
        return None

    def wait_for_completion(self, prompt_id, timeout_seconds=None):
        raise AssertionError

    def resolve_output_path(self, subfolder, filename):
        raise AssertionError


def test_request_visual_asset_logs_the_failure_lifecycle(db_session, tmp_path):
    # An always-offline client fails before ever touching the workflow
    # registry or asset storage, so these paths need not contain
    # anything real — just be configured so _root() does not raise.
    settings = Settings(comfyui_workflow_root=str(tmp_path), comfyui_asset_root=str(tmp_path))
    campaign = create_campaign(db_session, "Observability Failure", world_seed=1201)
    handler, teardown = _capture_visual_logs()
    try:
        request_visual_asset(
            db_session, _AlwaysOfflineClient(),
            entity_type="item_definition", entity_id="item_x", asset_type="ITEM_ILLUSTRATION",
            workflow_key="EVERREACH_ITEM", workflow_version="V3",
            prompt_text="a prompt", seed=1, campaign_id=campaign.id, settings=settings,
        )
    finally:
        teardown()

    combined = "\n".join(handler.messages)
    assert "event=request_created" in combined
    assert "event=failed" in combined
    assert "error_code='COMFYUI_OFFLINE'" in combined
    assert "duration_seconds=" in combined
