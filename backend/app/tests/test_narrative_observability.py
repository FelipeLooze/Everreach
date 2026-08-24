"""Phase 24P — Narrative Observability & Replay.

Two mechanisms: a contextvars-based correlation ID that every log
record emitted anywhere during a turn automatically carries (no
existing narrator.py/context_builder.py/intent_parser.py log call site
was changed to get this), and one structured summary line per turn
(app.ai.observability.log_narrative_request) mirroring the established
app.game.visual.observability.log_generation_event convention.
"""
import logging

from app.ai.observability import log_narrative_request
from app.core.logging import (
    current_narrative_request_id,
    get_logger,
    narrative_request_scope,
    new_narrative_request_id,
    with_narrative_request_id,
)


def test_current_narrative_request_id_defaults_to_a_sentinel_outside_any_scope():
    assert current_narrative_request_id() == "-"


def test_narrative_request_scope_sets_and_restores_the_id():
    assert current_narrative_request_id() == "-"
    with narrative_request_scope() as request_id:
        assert request_id.startswith("nr_")
        assert current_narrative_request_id() == request_id
    assert current_narrative_request_id() == "-"


def test_narrative_request_scope_accepts_an_explicit_id():
    with narrative_request_scope("nr_explicit") as request_id:
        assert request_id == "nr_explicit"
        assert current_narrative_request_id() == "nr_explicit"


def test_new_narrative_request_id_has_the_expected_prefix_and_is_unique():
    first = new_narrative_request_id()
    second = new_narrative_request_id()
    assert first.startswith("nr_")
    assert second.startswith("nr_")
    assert first != second


def test_with_narrative_request_id_wraps_a_function_call_in_a_scope():
    captured = []

    @with_narrative_request_id
    def _inner():
        captured.append(current_narrative_request_id())

    assert current_narrative_request_id() == "-"
    _inner()
    assert captured[0] != "-"
    assert captured[0].startswith("nr_")
    assert current_narrative_request_id() == "-"


def _capture_game_logs():
    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = get_logger("game")
    handler = _ListHandler()
    state = (logger.level, logger.disabled, logging.Logger.manager.disable)
    logging.disable(logging.NOTSET)
    logger.disabled = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger, handler, state, records


def _restore_game_logs(logger, handler, state) -> None:
    logger.removeHandler(handler)
    logger.setLevel(state[0])
    logger.disabled = state[1]
    logging.disable(state[2])


def test_log_narrative_request_renders_every_provided_field():
    logger, handler, state, records = _capture_game_logs()
    try:
        log_narrative_request(
            narrative_request_id="nr_abc123",
            campaign_id="campaign_1",
            character_id="char_1",
            active_npc_id="npc_1",
            player_input="Qual o seu nome?",
            model="qwen2.5:14b-instruct-q4_K_M",
            temperature=0.35,
            num_predict=500,
            context_fingerprint="deadbeef1234",
            context_chars=7103,
            estimated_tokens=1775,
            retrieved_source_ids=["doc_a", "doc_b"],
            narration_outcome="ACCEPTED_FIRST_PASS",
            narrator_unavailable=False,
            final_output="Meu nome é Aldric.",
            latency_ms=1234.5,
        )
    finally:
        _restore_game_logs(logger, handler, state)

    message = records[0].getMessage()
    assert "narrative_request_id='nr_abc123'" in message
    assert "campaign_id='campaign_1'" in message
    assert "character_id='char_1'" in message
    assert "active_npc_id='npc_1'" in message
    assert "player_input='Qual o seu nome?'" in message
    assert "model='qwen2.5:14b-instruct-q4_K_M'" in message
    assert "temperature=0.35" in message
    assert "num_predict=500" in message
    assert "context_fingerprint='deadbeef1234'" in message
    assert "context_chars=7103" in message
    assert "estimated_tokens=1775" in message
    assert "retrieved_source_ids='doc_a,doc_b'" in message
    assert "narration_outcome='ACCEPTED_FIRST_PASS'" in message
    assert "final_output='Meu nome é Aldric.'" in message
    assert "latency_ms=1234.5" in message


def test_log_narrative_request_omits_fields_that_were_not_given():
    logger, handler, state, records = _capture_game_logs()
    try:
        log_narrative_request(
            narrative_request_id="nr_abc123",
            campaign_id="campaign_1",
            character_id="char_1",
        )
    finally:
        _restore_game_logs(logger, handler, state)

    message = records[0].getMessage()
    assert "active_npc_id=" not in message
    assert "retrieved_source_ids=" not in message
    assert "final_output=" not in message


def test_log_narrative_request_clips_long_player_input_and_output():
    logger, handler, state, records = _capture_game_logs()
    try:
        log_narrative_request(
            narrative_request_id="nr_abc123",
            campaign_id="campaign_1",
            character_id="char_1",
            player_input="x" * 500,
            final_output="y" * 500,
        )
    finally:
        _restore_game_logs(logger, handler, state)

    message = records[0].getMessage()
    assert "x" * 500 not in message
    assert "…" in message


def test_log_narrative_request_uses_warning_level_when_narrator_is_unavailable():
    logger, handler, state, records = _capture_game_logs()
    try:
        log_narrative_request(
            narrative_request_id="nr_abc123",
            campaign_id="campaign_1",
            character_id="char_1",
            narrator_unavailable=True,
        )
    finally:
        _restore_game_logs(logger, handler, state)

    assert records[0].levelno == logging.WARNING


def test_log_narrative_request_defaults_to_info_level():
    logger, handler, state, records = _capture_game_logs()
    try:
        log_narrative_request(
            narrative_request_id="nr_abc123",
            campaign_id="campaign_1",
            character_id="char_1",
            narrator_unavailable=False,
        )
    finally:
        _restore_game_logs(logger, handler, state)

    assert records[0].levelno == logging.INFO


# --- Integration: app.game.engine.resolve_action's real wiring ---


def _capture_logs(category: str):
    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = get_logger(category)
    handler = _ListHandler()
    state = (logger.level, logger.disabled, logging.Logger.manager.disable)
    logging.disable(logging.NOTSET)
    logger.disabled = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return logger, handler, state, records


def test_resolve_action_emits_a_correlated_summary_and_tags_other_logs_the_same(db_session):
    from app.ai.llm_service import LLMService
    from app.core.logging import _NarrativeRequestIdFilter
    from app.game import engine
    from app.game.character.service import create_character
    from app.game.world.seed import create_campaign, seed_initial_region

    class _FakeLLM(LLMService):
        def generate(self, system: str, prompt: str) -> str:
            if "intent" in system.lower():
                return '{"intent": "FREEFORM"}'
            return "Nada de especial acontece."

    campaign = create_campaign(db_session, "Observabilidade Integrada")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.commit()

    game_logger, game_handler, game_state_, game_records = _capture_logs("game")
    narration_logger, narration_handler, narration_state, narration_records = _capture_logs(
        "narration"
    )
    # Self-contained root handler+filter: does not depend on
    # app.core.logging.configure_logging() having already run somewhere
    # earlier in the suite (a real, process-global-state risk this
    # codebase's own tests already document elsewhere). A logger-level
    # filter would NOT do this — Python only consults a logger's own
    # .filters at the record's ORIGINATING logger, never re-checking an
    # ancestor's during propagation — so this must be a HANDLER filter,
    # exactly matching configure_logging()'s own real setup.
    root_logger = logging.getLogger("everreach")
    root_handler = logging.NullHandler()
    root_handler.addFilter(_NarrativeRequestIdFilter())
    root_logger.addHandler(root_handler)
    try:
        engine.resolve_action(db_session, _FakeLLM(), campaign.id, character.id, "Eu olho ao redor.")
    finally:
        root_logger.removeHandler(root_handler)
        _restore_game_logs(game_logger, game_handler, game_state_)
        _restore_game_logs(narration_logger, narration_handler, narration_state)

    summary_records = [r for r in game_records if r.getMessage().startswith("narrative_request ")]
    assert len(summary_records) == 1
    summary_message = summary_records[0].getMessage()
    assert f"campaign_id='{campaign.id}'" in summary_message
    assert f"character_id='{character.id}'" in summary_message

    # Every record (both "game" and "narration" loggers) emitted during
    # this call carries the SAME narrative_request_id — the actual
    # correlation claim, not just that the summary line exists.
    request_ids = {
        getattr(record, "narrative_request_id", None)
        for record in [*game_records, *narration_records]
        if getattr(record, "narrative_request_id", "-") != "-"
    }
    assert len(request_ids) == 1
