"""Phase 23D-Q — GPU Resource Coordination.

Ollama (LLM inference) and ComfyUI (visual generation) share one local
GPU with limited VRAM. This module manages neither service's lifecycle
and neither model's residency — it only ever prevents two heavy GPU
workloads from running AT THE SAME TIME. Both servers stay running
continuously; nothing here starts, stops, or restarts Ollama/ComfyUI,
and nothing here touches Ollama's keep_alive policy.

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
"""
import threading
from contextlib import contextmanager
from typing import Iterator

from app.core.logging import get_logger

logger = get_logger("gpu")

_lock = threading.Lock()


@contextmanager
def gpu_heavy_operation(task: str) -> Iterator[None]:
    """Serializes GPU-heavy work across the whole process. `task` is a
    short label (e.g. "LLM_TASK", "VISUAL_TASK") used only for logging
    — this function never branches on it, and callers outside
    app.ai/app.game.visual should not need this at all."""
    had_to_wait = not _lock.acquire(blocking=False)
    if had_to_wait:
        logger.info("gpu_coordinator waiting task=%s", task)
        _lock.acquire()
    logger.info("gpu_coordinator acquired task=%s", task)
    try:
        yield
    finally:
        logger.info("gpu_coordinator released task=%s", task)
        _lock.release()
