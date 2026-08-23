"""Phase 23D-Q — GPU Resource Coordination.

Ollama (LLM inference) and ComfyUI (visual generation) share one local
GPU with limited VRAM. This module never starts, stops, or restarts
either service — it only ever prevents two heavy GPU workloads from
running AT THE SAME TIME.

ONE HEAVY GPU WORKLOAD AT A TIME (spec, mandatory): a single process-
local threading.Lock, deliberately NOT asyncio.Lock. Every route in
this codebase is a sync `def`, which Starlette dispatches to its own
worker thread (anyio.to_thread.run_sync) — two concurrent HTTP
requests genuinely run on two different OS threads within this one
process. An asyncio.Lock only serializes coroutines sharing a single
event loop; it would not serialize across those threads. No
distributed infra (Redis/Celery/RabbitMQ/Kafka) — single-user, single
machine, single GPU; a general-purpose scheduler would be solving a
problem this app does not have.

Only the actual GPU-bound call should ever be wrapped in
gpu_heavy_operation — Ollama's own generate/embed HTTP call
(app.ai.llm_service.OllamaLLMService), or the ComfyUI submit_workflow
-> wait_for_completion span (app.game.visual.service.
request_visual_asset) — never a database transaction, matching the
same discipline app.game.visual.service already applies to its own DB
transaction boundary ("do not keep a transaction open while waiting").
The two call paths never nest (confirmed: engine.py/narrator.py never
call into app.game.visual, and app.game.visual never calls
llm_service), so a plain non-reentrant lock cannot self-deadlock here.

Phase 23D-Q.1 measured real residency contention on the actual dev
machine (RTX 4070 Ti, 12GB VRAM): with the configured Ollama model
resident, an otherwise-identical ComfyUI generation took ~6x longer
(15.97s vs 2.69s, same warm/cached graph state both times) and peak
free VRAM dropped to ~378MB — a real, reproducible degradation, not
compute contention (23D-Q already solved that) but memory RESIDENCY
contention. 23D-Q.2 (this module's set_llm_release_hook) is the
directly-evidenced fix: right after acquiring the lock for a
VISUAL_TASK, ask the LLM service to give up its resident model before
the caller's ComfyUI work runs. This module still does not decide
WHETHER/HOW that happens — it only calls back into whatever hook
app.ai.llm_service registered (a real Ollama unload) or none at all
(a safe default for any non-GPU-resident LLMService), and never
reaches into app.ai itself (no import of it here, keeping this module
dependency-free — see build_llm_service's own registration call).
"""
import threading
from contextlib import contextmanager
from typing import Callable, Iterator

from app.core.logging import get_logger

logger = get_logger("gpu")

_lock = threading.Lock()
_llm_release_hook: Callable[[], None] | None = None


def set_llm_release_hook(hook: Callable[[], None] | None) -> None:
    """Registered by app.ai.llm_service.build_llm_service (or a test),
    so a VISUAL_TASK can ask the LLM to release its GPU residency right
    before the caller's ComfyUI work runs. Called ONLY while this
    module's own lock is already held (see gpu_heavy_operation) — a
    hook must never itself call gpu_heavy_operation, since
    threading.Lock is not reentrant and that would deadlock.
    None (the default) is a real, valid state: no hook means no
    release happens, exactly today's pre-23D-Q.2 behavior."""
    global _llm_release_hook
    _llm_release_hook = hook


@contextmanager
def gpu_heavy_operation(task: str) -> Iterator[None]:
    """Serializes GPU-heavy work across the whole process. `task` is a
    short label (e.g. "LLM_TASK", "VISUAL_TASK") used for logging, and
    — for "VISUAL_TASK" specifically — to trigger the registered LLM
    release hook (23D-Q.2) once the lock is safely held."""
    had_to_wait = not _lock.acquire(blocking=False)
    if had_to_wait:
        logger.info("gpu_coordinator waiting task=%s", task)
        _lock.acquire()
    logger.info("gpu_coordinator acquired task=%s", task)
    try:
        if task == "VISUAL_TASK" and _llm_release_hook is not None:
            try:
                _llm_release_hook()
            except Exception as exc:  # best-effort — never blocks the caller
                logger.warning("gpu_coordinator llm_release_hook failed: %s", exc)
        yield
    finally:
        logger.info("gpu_coordinator released task=%s", task)
        _lock.release()
