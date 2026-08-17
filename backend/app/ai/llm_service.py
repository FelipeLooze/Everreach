from abc import ABC, abstractmethod

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("llm")


class LLMServiceError(Exception):
    """Raised when the configured LLM backend is unreachable or errors out.
    Callers must surface this clearly — never silently fabricate a response."""


class LLMService(ABC):
    @abstractmethod
    def generate(self, system: str, prompt: str) -> str:
        """Return the model's raw text completion for a single-turn system+prompt call."""


class OllamaLLMService(LLMService):
    """Talks to a local Ollama server. This is the ONLY place that knows about Ollama's
    HTTP API — swapping to llama.cpp / LM Studio / another OpenAI-compatible server later
    means writing a new class here, not touching the Game Engine or callers."""

    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def generate(self, system: str, prompt: str) -> str:
        try:
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
                    "options": {"temperature": 0.35},
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


def build_llm_service(settings: Settings | None = None) -> LLMService:
    settings = settings or get_settings()
    return OllamaLLMService(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout=settings.ollama_timeout_seconds,
    )
