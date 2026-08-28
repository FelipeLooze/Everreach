"""Phase 24K — the one place every call site asks an LLMService for a
completion, so provider/model/purpose/latency/tokens observability
(app.ai.observability.log_generation_call) is threaded in exactly once
rather than duplicated at each of intent_parser.py's, narrator.py's, and
validation/contract.py's own generate() call sites. Does not change
LLMService.generate()'s own contract (still system, prompt -> str) —
this wraps a call, it is not a second parallel abstraction.
"""
import time

from app.ai.llm_service import LLMService, LLMServiceError
from app.ai.observability import log_generation_call


def call_llm(
    llm_service: LLMService,
    system: str,
    prompt: str,
    *,
    purpose: str,
    attempt: int = 1,
) -> str:
    """purpose identifies the logical role (for example INTENT, NARRATIVE,
    REPAIR or ECONOMIC_PRICE_PROPOSAL). Logs the call
    (success or failure) via log_generation_call, then returns the raw
    text or re-raises LLMServiceError unchanged — callers keep their
    existing try/except LLMServiceError handling verbatim."""
    started = time.monotonic()
    try:
        text = llm_service.generate(system, prompt)
    except LLMServiceError as exc:
        log_generation_call(
            purpose=purpose,
            provider=llm_service.provider_name,
            model=llm_service.model_name,
            attempt=attempt,
            latency_ms=(time.monotonic() - started) * 1000,
            status="ERROR",
            error_message=str(exc),
        )
        raise

    metadata = llm_service.last_generation_metadata
    log_generation_call(
        purpose=purpose,
        provider=llm_service.provider_name,
        model=llm_service.model_name,
        attempt=attempt,
        latency_ms=metadata.latency_ms if metadata else (time.monotonic() - started) * 1000,
        prompt_tokens=metadata.prompt_tokens if metadata else None,
        completion_tokens=metadata.completion_tokens if metadata else None,
        total_tokens=metadata.total_tokens if metadata else None,
        finish_reason=metadata.finish_reason if metadata else None,
        request_id=metadata.request_id if metadata else None,
        status="OK",
    )
    return text
