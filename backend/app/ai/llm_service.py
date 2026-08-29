from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import time

import httpx

from app.core.config import Settings, get_settings
from app.core.gpu_coordinator import gpu_heavy_operation, set_llm_release_hook
from app.core.logging import get_logger

logger = get_logger("llm")


@dataclass(frozen=True)
class GenerationMetadata:
    """Phase 24K — the small, provider-neutral result shape the spec asks
    for: enough for observability to report what actually answered a
    turn without needing a second parallel abstraction alongside
    LLMService.generate()'s own plain-string contract (which stays
    unchanged — dozens of existing callers/test doubles only implement
    that). Populated by a concrete service after each generate() call,
    read back via LLMService.last_generation_metadata; any field a given
    provider doesn't report (e.g. Ollama has no request_id) stays None."""

    provider: str
    model: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    request_id: str | None = None


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

    @property
    def provider_name(self) -> str:
        """Phase 24K — observability identifier ("ollama"/"openrouter").
        Not abstract: a safe, generic default so the dozens of existing
        test-double LLMService subclasses across the suite need no
        changes; only a real provider implementation overrides this."""
        return "unknown"

    @property
    def model_name(self) -> str:
        """Phase 24K — the specific model this service talks to, for
        observability. Same "not abstract, safe default" reasoning as
        provider_name above."""
        return "unknown"

    @property
    def last_generation_metadata(self) -> GenerationMetadata | None:
        """Phase 24K — metadata for the MOST RECENT generate() call this
        instance made (tokens/finish_reason/latency/request_id, whatever
        the provider actually returned), or None before any call has
        completed. Default None — a test double need not populate this
        for its result to remain a valid, complete LLMService."""
        return None

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
        self._last_generation_metadata: GenerationMetadata | None = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def last_generation_metadata(self) -> GenerationMetadata | None:
        return self._last_generation_metadata

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
        started = time.monotonic()
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
        # Phase 24K — the same metadata, in the small provider-neutral
        # shape observability now reads regardless of which provider
        # answered; total latency (not just Ollama's own eval_duration)
        # so it's directly comparable to OpenRouterLLMService's own.
        self._last_generation_metadata = GenerationMetadata(
            provider="ollama",
            model=self._model,
            latency_ms=(time.monotonic() - started) * 1000,
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            total_tokens=(
                (data.get("prompt_eval_count") or 0) + (data.get("eval_count") or 0)
                if data.get("prompt_eval_count") is not None or data.get("eval_count") is not None
                else None
            ),
            finish_reason=data.get("done_reason"),
            request_id=None,
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


def _openrouter_error_detail(response: httpx.Response) -> str | None:
    """Mirrors _ollama_error_detail's own reasoning: OpenRouter's error
    body shape is {"error": {"message": "...", "code": ..., ...}} (an
    OBJECT, not a bare string like Ollama's) — best-effort, must never
    itself raise out of an error-handling path."""
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message
    elif isinstance(error, str) and error:
        return error
    return None


class OpenRouterLLMService(LLMService):
    """Phase 24K — talks to OpenRouter's OpenAI-compatible Chat
    Completions API. This is the ONLY place that knows about
    OpenRouter's HTTP shape, mirroring OllamaLLMService's own "one class
    per provider" boundary — narrator.py/intent_parser.py/engine.py
    never see this class, only the shared LLMService.generate() contract.

    Deliberately conservative about what it sends: only model/messages/
    temperature/max_tokens, per the governing spec's own instruction not
    to assume every OpenRouter model supports every optional OpenAI
    parameter. No reasoning-control parameter is sent — if a model
    returns extra reasoning content alongside its answer, this class
    only ever reads message["content"], so reasoning text can never
    reach the player, RAG, conversation history, or logs by construction
    (nothing here ever looks at any other message field)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 180.0,
        temperature: float = 0.35,
        max_tokens: int | None = 500,
        http_referer: str = "",
        app_title: str = "",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._http_referer = http_referer
        self._app_title = app_title
        self._last_generation_metadata: GenerationMetadata | None = None

    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def last_generation_metadata(self) -> GenerationMetadata | None:
        return self._last_generation_metadata

    def generate(self, system: str, prompt: str) -> str:
        if not self._api_key:
            # Checked before any network call — never a bare 401 from a
            # request we should never have sent.
            raise LLMServiceError(
                "OPENROUTER_API_KEY is not configured. Set it in the environment "
                "before selecting the openrouter provider."
            )

        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._http_referer:
            headers["HTTP-Referer"] = self._http_referer
        if self._app_title:
            headers["X-Title"] = self._app_title

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": self._temperature,
            # Phase 24K — confirmed necessary via a real live call, not
            # speculative: nvidia/nemotron-3-ultra-550b-a55b:free, asked
            # with no "reasoning" parameter at all, returned its raw
            # chain-of-thought INSIDE message.content itself ("Let me
            # analyze the context carefully...") rather than routing it
            # to the separate message.reasoning field OpenRouter's own
            # docs describe as the normal split. "exclude" is OpenRouter's
            # own documented, provider-neutral field (audited via its
            # current reasoning-tokens docs before adding this) — the
            # model may still reason internally, but is told not to
            # return it in the response at all, closing this at its
            # actual source rather than trying to detect/strip a chain-
            # of-thought preamble out of already-returned content.
            "reasoning": {"exclude": True},
        }
        if self._max_tokens is not None:
            payload["max_tokens"] = self._max_tokens

        started = time.monotonic()
        try:
            with gpu_heavy_operation("LLM_TASK"):
                response = httpx.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )
        except httpx.ConnectError as exc:
            logger.warning("OpenRouter unreachable: %s", exc)
            raise LLMServiceError(f"Could not reach OpenRouter: {exc}") from exc
        except httpx.TimeoutException as exc:
            logger.warning("OpenRouter request timed out: %s", exc)
            raise LLMServiceError("OpenRouter took too long to respond.") from exc
        latency_ms = (time.monotonic() - started) * 1000

        if response.status_code != 200:
            detail = _openrouter_error_detail(response)
            if response.status_code == 401:
                logger.warning("OpenRouter authentication failed: %s", detail or "no detail")
                raise LLMServiceError(
                    f"OpenRouter authentication failed: {detail or 'invalid or missing API key'}"
                )
            if response.status_code == 429:
                # Phase 24K — identified explicitly as RATE_LIMITED per
                # the spec: no retry, no silent fallback to another
                # provider, truthful reporting so an evaluation run
                # never mistakes "quota exhausted" for "model answered
                # with nothing."
                logger.warning(
                    "OpenRouter rate limit reached (model=%s): %s", self._model, detail or "no detail"
                )
                raise LLMServiceError(
                    f"OpenRouter rate limit reached for {self._model}: {detail or 'rate limited'}"
                )
            if response.status_code == 404:
                logger.warning("OpenRouter model unavailable (model=%s): %s", self._model, detail)
                raise LLMServiceError(
                    f"OpenRouter model unavailable ({self._model}): {detail or 'not found'}"
                )
            if response.status_code >= 500:
                logger.warning(
                    "OpenRouter server error %s (model=%s): %s", response.status_code, self._model, detail
                )
                raise LLMServiceError(
                    f"OpenRouter server error ({response.status_code}): {detail or 'provider unavailable'}"
                )
            logger.warning(
                "OpenRouter request failed %s (model=%s): %s", response.status_code, self._model, detail
            )
            raise LLMServiceError(
                f"OpenRouter request failed ({response.status_code}): {detail or 'unknown error'}"
            )

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("OpenRouter returned a malformed (non-JSON) response: %s", exc)
            raise LLMServiceError("OpenRouter returned a malformed response.") from exc

        if not isinstance(data, dict):
            logger.warning("OpenRouter returned a non-object response body.")
            raise LLMServiceError("OpenRouter returned an unexpected response shape.")

        # Phase 24K — an error payload can arrive inside an otherwise-200
        # response (documented OpenRouter behavior for some upstream
        # provider failures) — must never be silently treated as an
        # empty generated response, same discipline as Ollama's own
        # in-body error check.
        error = data.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else str(error)
            logger.warning("OpenRouter reported an error payload: %s", message)
            raise LLMServiceError(f"OpenRouter error: {message}")

        choices = data.get("choices")
        if not choices or not isinstance(choices, list):
            logger.warning("OpenRouter response had no choices: keys=%s", list(data.keys()))
            raise LLMServiceError("OpenRouter returned no completion choices.")

        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            logger.warning("OpenRouter response had no assistant content.")
            raise LLMServiceError("OpenRouter returned an empty completion (no assistant content).")

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        finish_reason = first_choice.get("finish_reason")
        request_id = data.get("id")

        self._last_generation_metadata = GenerationMetadata(
            provider="openrouter",
            model=self._model,
            latency_ms=latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
            request_id=request_id if isinstance(request_id, str) else None,
        )
        logger.debug(
            "OpenRouter generation metadata: model=%s finish_reason=%s prompt_tokens=%s "
            "completion_tokens=%s total_tokens=%s latency_ms=%.0f request_id=%s",
            self._model,
            finish_reason,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
            latency_ms,
            request_id,
        )
        return content.strip()


def _build_ollama_service(settings: Settings, model: str) -> OllamaLLMService:
    return OllamaLLMService(
        base_url=settings.ollama_base_url,
        model=model,
        timeout=settings.ollama_timeout_seconds,
        embedding_model=settings.ollama_embedding_model,
        num_predict=settings.ollama_num_predict,
        temperature=settings.ollama_temperature,
        keep_alive=settings.ollama_keep_alive,
    )


def _build_openrouter_service(settings: Settings, model: str) -> OpenRouterLLMService:
    return OpenRouterLLMService(
        api_key=settings.openrouter_api_key,
        model=model,
        base_url=settings.openrouter_base_url,
        timeout=settings.openrouter_timeout_seconds,
        temperature=settings.openrouter_temperature,
        max_tokens=settings.openrouter_max_tokens,
        http_referer=settings.openrouter_http_referer,
        app_title=settings.openrouter_app_title,
    )


def _build_service_for_role(settings: Settings, provider: str, model: str) -> LLMService:
    normalized = (provider or "ollama").strip().lower()
    if normalized == "openrouter":
        if not model:
            raise LLMServiceError(
                "An OpenRouter model must be configured (e.g. NARRATIVE_LLM_MODEL) "
                "when provider=openrouter — the free router alias is deliberately "
                "not used here, per the exact-model-ID requirement."
            )
        return _build_openrouter_service(settings, model)
    if normalized == "ollama":
        return _build_ollama_service(settings, model or settings.ollama_model)
    raise LLMServiceError(f"Unknown LLM provider: {provider!r} (expected 'ollama' or 'openrouter')")


def build_llm_service(settings: Settings | None = None) -> LLMService:
    """Build the default service used outside the per-turn role split.

    It follows the narrative provider so disabling local Ollama also covers
    economic and world-generation helpers; no hidden local call path remains.
    """
    settings = settings or get_settings()
    service = _build_service_for_role(
        settings,
        settings.narrative_llm_provider,
        settings.narrative_llm_model,
    )
    # Phase 23D-Q.2 — the coordinator calls this back right before a
    # VISUAL_TASK runs, so ComfyUI gets the full VRAM budget instead of
    # competing with a resident LLM. Registered generically (works for
    # any LLMService — release_gpu_residency defaults to a no-op) so
    # this stays correct if the concrete service ever changes.
    set_llm_release_hook(service.release_gpu_residency)
    return service


def build_role_llm_services(settings: Settings | None = None) -> tuple[LLMService, LLMService]:
    """Phase 24K — returns (intent_service, narrative_service), built
    independently from INTENT_LLM_PROVIDER/MODEL and NARRATIVE_LLM_
    PROVIDER/MODEL. Both default to provider="ollama" with an empty
    model (falls back to settings.ollama_model) — an unmodified .env
    produces two separate OllamaLLMService instances pointed at the
    exact same server/model, functionally identical to the single
    pre-24K build_llm_service() default.

    Registers ONE combined GPU-release hook covering every distinct
    service actually constructed (not just one) — a real fix for a real
    gap: registering only the narrative service's hook would silently
    stop releasing the intent service's own resident model whenever the
    two providers differ (e.g. intent=Ollama, narrative=OpenRouter would
    otherwise overwrite Ollama's real release hook with OpenRouter's
    no-op)."""
    settings = settings or get_settings()
    intent_service = _build_service_for_role(
        settings, settings.intent_llm_provider, settings.intent_llm_model
    )
    narrative_service = _build_service_for_role(
        settings, settings.narrative_llm_provider, settings.narrative_llm_model
    )

    distinct_services = [intent_service]
    if narrative_service is not intent_service:
        distinct_services.append(narrative_service)

    def _release_all() -> None:
        for service in distinct_services:
            service.release_gpu_residency()

    set_llm_release_hook(_release_all)
    return intent_service, narrative_service
