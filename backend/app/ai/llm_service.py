from abc import ABC, abstractmethod
import json

import httpx

from app.core.config import Settings, get_settings
from app.core.gpu_coordinator import gpu_heavy_operation, set_llm_release_hook
from app.core.logging import get_logger

logger = get_logger("llm")


def _ollama_error_detail(response: httpx.Response) -> str | None:
    """Phase 24O — Ollama returns a JSON body ({"error": "..."}) even on
    a non-2xx response (verified live: a missing model returns 404 with
    {"error": "model 'x' not found"}); httpx's own exception message
    ("Client error '404 Not Found' for url ...") never includes this,
    so without this every HTTP-level failure — model missing, malformed
    request, anything else Ollama itself distinguishes — collapsed into
    the same generic, undiagnosable message. Best-effort: the body might
    not be JSON at all (a proxy error page, a truncated response), which
    must never itself raise out of an error-handling path."""
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, str) and error:
            return error
    return None


class LLMServiceError(Exception):
    """Raised when the configured LLM backend is unreachable or errors out.
    Callers must surface this clearly — never silently fabricate a response."""


class LLMService(ABC):
    @abstractmethod
    def generate(self, system: str, prompt: str) -> str:
        """Return the model's raw text completion for a single-turn system+prompt call."""

    def embed(self, text: str) -> list[float]:
        """Phase 18H — return a semantic embedding vector for text.

        Not abstract: generation and embedding are separate capabilities
        (a provider, or a local model, may support one without the
        other), and dozens of existing test doubles across the suite
        only ever needed to implement generate(). The base implementation
        always raises — callers (app.ai.retrieval.semantic) already treat
        LLMServiceError as "embeddings unavailable" and degrade to no
        semantic candidates rather than crashing, exactly like generate()
        failures already degrade the intent parser to FREEFORM."""
        raise LLMServiceError("This LLMService does not support embeddings.")

    def release_gpu_residency(self) -> None:
        """Phase 23D-Q.2 — best-effort hint that this service should give
        up whatever GPU memory it is holding resident, if it can. Not
        abstract, same reasoning as embed(): most LLMServices (any
        remote/API-backed one, every test double) have nothing local to
        release. The default is a safe no-op; only a real local-GPU-
        backed service (OllamaLLMService below) needs a real one."""
        return None


class OllamaLLMService(LLMService):
    """Talks to a local Ollama server. This is the ONLY place that knows about Ollama's
    HTTP API — swapping to llama.cpp / LM Studio / another OpenAI-compatible server later
    means writing a new class here, not touching the Game Engine or callers."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float,
        embedding_model: str | None = None,
        num_predict: int | None = None,
        temperature: float = 0.35,
        keep_alive: str = "5m",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._embedding_model = embedding_model
        self._num_predict = num_predict
        self._temperature = temperature
        self._keep_alive = keep_alive

    def generate(self, system: str, prompt: str) -> str:
        options = {"temperature": self._temperature}
        if self._num_predict is not None:
            # Phase 24A.1 — verified live against this exact server that
            # num_predict is a real, respected cap (requesting 30
            # returned exactly eval_count=30, done_reason="length"), not
            # a documentation guess. Without it, generation has no
            # ceiling at all, which is part of how the model could keep
            # going into a fabricated multi-turn continuation instead of
            # stopping after one coherent beat.
            options["num_predict"] = self._num_predict
        try:
            # Phase 23D-Q — Ollama and ComfyUI share one local GPU;
            # only the actual network round trip (where Ollama does the
            # real inference) is held under the lock, never anything
            # before/after it.
            with gpu_heavy_operation("LLM_TASK"):
                response = httpx.post(
                    f"{self._base_url}/api/generate",
                    json={
                        "model": self._model,
                        "system": system,
                        "prompt": prompt,
                        "stream": False,
                        # Some local models (e.g. qwen3) are "thinking" models that emit a
                        # separate reasoning trace by default. We only want the final answer.
                        "think": False,
                        "options": options,
                        "keep_alive": self._keep_alive,
                    },
                    timeout=self._timeout,
                )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            logger.warning("Ollama unreachable: %s", exc)
            raise LLMServiceError(f"Could not reach Ollama at {self._base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            logger.warning("Ollama request timed out: %s", exc)
            raise LLMServiceError("The local model took too long to respond.") from exc
        except httpx.HTTPError as exc:
            # Phase 24O — includes Ollama's own error detail when the
            # response body has one (e.g. "model 'x' not found" on a 404
            # from a misconfigured OLLAMA_MODEL) instead of only httpx's
            # generic "Client error '404 Not Found'..." message.
            detail = _ollama_error_detail(exc.response) if isinstance(exc, httpx.HTTPStatusError) else None
            logger.warning("Ollama request failed: %s%s", exc, f" ({detail})" if detail else "")
            raise LLMServiceError(
                f"Ollama request failed: {detail or exc}"
            ) from exc

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            # Phase 24O — a 200 response whose body isn't valid JSON at
            # all (a malformed response, not a documented Ollama failure
            # mode observed live, but never allowed to escape as a raw,
            # untyped exception either).
            logger.warning("Ollama returned a malformed (non-JSON) response: %s", exc)
            raise LLMServiceError("Ollama returned a malformed response.") from exc

        error_detail = data.get("error") if isinstance(data, dict) else None
        if error_detail:
            # Phase 24O — defensive: an error reported inside an
            # otherwise-200 body (not observed live against this Ollama
            # version, which uses HTTP status codes for the failures
            # tested, but Ollama's own API is not contractually
            # guaranteed to always do so). Must never be silently
            # treated as an empty generated response.
            logger.warning("Ollama reported a generation error: %s", error_detail)
            raise LLMServiceError(f"Ollama generation failed: {error_detail}")

        # Phase 24B — generation result metadata, DEBUG-only. Ollama's
        # own response already carries this; nothing previously looked
        # at it. Doesn't change generate()'s return contract (still a
        # plain string) — a future Phase 24P (narrative observability)
        # is where this earns a real correlation ID and persisted trace;
        # this just makes it visible today without that larger piece.
        eval_duration_ms = data.get("eval_duration", 0) / 1_000_000
        logger.debug(
            "Ollama generation metadata: model=%s eval_count=%s eval_duration_ms=%.0f "
            "prompt_eval_count=%s done_reason=%s",
            self._model,
            data.get("eval_count"),
            eval_duration_ms,
            data.get("prompt_eval_count"),
            data.get("done_reason"),
        )
        text = data.get("response", "")
        return text.strip()

    def embed(self, text: str) -> list[float]:
        if not self._embedding_model:
            raise LLMServiceError("No Ollama embedding model configured.")
        try:
            with gpu_heavy_operation("LLM_TASK"):
                response = httpx.post(
                    f"{self._base_url}/api/embed",
                    json={"model": self._embedding_model, "input": text},
                    timeout=self._timeout,
                )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            logger.warning("Ollama unreachable: %s", exc)
            raise LLMServiceError(f"Could not reach Ollama at {self._base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            logger.warning("Ollama request timed out: %s", exc)
            raise LLMServiceError("The local model took too long to respond.") from exc
        except httpx.HTTPError as exc:
            detail = _ollama_error_detail(exc.response) if isinstance(exc, httpx.HTTPStatusError) else None
            logger.warning("Ollama embedding request failed: %s%s", exc, f" ({detail})" if detail else "")
            raise LLMServiceError(f"Ollama embedding request failed: {detail or exc}") from exc

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Ollama returned a malformed (non-JSON) embedding response: %s", exc)
            raise LLMServiceError("Ollama returned a malformed embedding response.") from exc

        error_detail = data.get("error") if isinstance(data, dict) else None
        if error_detail:
            logger.warning("Ollama reported an embedding error: %s", error_detail)
            raise LLMServiceError(f"Ollama embedding failed: {error_detail}")

        embeddings = data.get("embeddings") or []
        if not embeddings:
            raise LLMServiceError("Ollama returned no embedding.")
        return embeddings[0]

    def release_gpu_residency(self) -> None:
        """Phase 23D-Q.2 — measured on this exact machine (RTX 4070 Ti,
        12GB VRAM): with hermes3:8b-llama3.1-q4_K_M resident, an
        otherwise-identical warm ComfyUI generation took ~6x longer
        (15.97s vs 2.69s) and peak free VRAM dropped to ~378MB — real,
        reproducible degradation, not a hypothetical one. This asks
        Ollama to unload the model immediately (keep_alive=0) rather
        than waiting out the normal 5-minute idle window; the next real
        generate()/embed() call simply reloads it cold, exactly like
        today's behavior on a fresh server start.

        Deliberately does NOT use gpu_heavy_operation itself — the
        gpu_coordinator only ever calls this while it already holds the
        lock (see set_llm_release_hook's docstring), and threading.Lock
        is not reentrant. Best-effort and silent: a failure here must
        never block the visual generation that triggered it — worst
        case the model just stays resident a little longer, exactly
        today's pre-23D-Q.2 behavior."""
        try:
            httpx.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": "", "keep_alive": 0},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            logger.info("Could not release Ollama GPU residency: %s", exc)


def build_llm_service(settings: Settings | None = None) -> LLMService:
    settings = settings or get_settings()
    service = OllamaLLMService(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout=settings.ollama_timeout_seconds,
        embedding_model=settings.ollama_embedding_model,
        num_predict=settings.ollama_num_predict,
        temperature=settings.ollama_temperature,
        keep_alive=settings.ollama_keep_alive,
    )
    # Phase 23D-Q.2 — the coordinator calls this back right before a
    # VISUAL_TASK runs, so ComfyUI gets the full VRAM budget instead of
    # competing with a resident LLM. Registered generically (works for
    # any LLMService — release_gpu_residency defaults to a no-op) so
    # this stays correct if the concrete service ever changes.
    set_llm_release_hook(service.release_gpu_residency)
    return service
