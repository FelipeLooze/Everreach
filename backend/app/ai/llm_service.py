from abc import ABC, abstractmethod

import httpx

from app.core.config import Settings, get_settings
from app.core.gpu_coordinator import gpu_heavy_operation, set_llm_release_hook
from app.core.logging import get_logger

logger = get_logger("llm")


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
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._embedding_model = embedding_model
        self._num_predict = num_predict

    def generate(self, system: str, prompt: str) -> str:
        options = {"temperature": 0.35}
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
                        # Keep the model loaded between requests — a cold load can take
                        # 20s+ for an 8B model, which would otherwise hit on every action.
                        "keep_alive": "5m",
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
            logger.warning("Ollama request failed: %s", exc)
            raise LLMServiceError(f"Ollama request failed: {exc}") from exc

        data = response.json()
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
            logger.warning("Ollama embedding request failed: %s", exc)
            raise LLMServiceError(f"Ollama embedding request failed: {exc}") from exc

        data = response.json()
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
    )
    # Phase 23D-Q.2 — the coordinator calls this back right before a
    # VISUAL_TASK runs, so ComfyUI gets the full VRAM budget instead of
    # competing with a resident LLM. Registered generically (works for
    # any LLMService — release_gpu_residency defaults to a no-op) so
    # this stays correct if the concrete service ever changes.
    set_llm_release_hook(service.release_gpu_residency)
    return service
