from contextlib import contextmanager
import contextvars
import functools
import logging
import sys
import uuid

CATEGORIES = [
    "game",
    "db",
    "simulation",
    "llm",
    "narration",
    "context",
    "api",
    "visual",
    "gpu",
]


# Phase 24P — Narrative Observability & Replay. A contextvars-based
# correlation ID, not a value threaded manually through every function
# signature: dozens of existing logger.debug/warning/error calls across
# narrator.py, context_builder.py, and intent_parser.py already carry
# exactly the raw output/validation findings/repair attempts the spec
# asks to associate with a request — the only thing missing was a way
# to find every line belonging to ONE turn without reconstructing by
# timestamp. A logging.Filter injects the current value into every
# LogRecord automatically, so none of those existing call sites (or
# their call signatures) need to change at all — "use current logging
# conventions" (spec's own words), not a parallel structured-logging or
# telemetry system.
_narrative_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "narrative_request_id", default="-"
)


class _NarrativeRequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.narrative_request_id = _narrative_request_id.get()
        return True


def new_narrative_request_id() -> str:
    return f"nr_{uuid.uuid4().hex[:12]}"


def current_narrative_request_id() -> str:
    return _narrative_request_id.get()


@contextmanager
def narrative_request_scope(request_id: str | None = None):
    """Sets the correlation ID every log record emitted inside this
    scope will carry, and restores the previous value on exit (a nested
    scope — not expected in practice, but must not corrupt an outer
    one)."""
    token = _narrative_request_id.set(request_id or new_narrative_request_id())
    try:
        yield _narrative_request_id.get()
    finally:
        _narrative_request_id.reset(token)


def with_narrative_request_id(fn):
    """Wraps a whole function call in narrative_request_scope() without
    touching its body/indentation — for wrapping an existing, large
    function (app.game.engine.resolve_action) at its definition site
    instead of re-indenting its entire implementation."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with narrative_request_scope():
            return fn(*args, **kwargs)

    return wrapper


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_NarrativeRequestIdFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] [req=%(narrative_request_id)s] %(message)s"
        )
    )

    root = logging.getLogger("everreach")
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False


def get_logger(category: str) -> logging.Logger:
    if category not in CATEGORIES:
        raise ValueError(f"Unknown logging category: {category}")
    return logging.getLogger(f"everreach.{category}")
