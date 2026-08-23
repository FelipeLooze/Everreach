"""Phase 23D-B — ComfyUI Client Foundation.

ONE centralized integration point for talking to a local ComfyUI
server, mirroring app.ai.llm_service's shape exactly (ABC + concrete
httpx-based implementation + build_* factory + a settings-driven
enabled/disabled switch) since that is the repository's own established
pattern for an optional local external service. No other module should
open a raw HTTP connection to ComfyUI.

This client is deliberately mechanical: submit_workflow() accepts
whatever node-graph dict it is given and does not itself decide
whether that graph is "trusted" — that enforcement belongs to the
Visual Workflow Registry (23D-C) and VisualAssetService (23D-I), which
are the only callers allowed to build a graph in the first place. The
client has no opinion about Canon, campaigns, or entities.

COMFYUI FAILURE != GAMEPLAY FAILURE: is_available() never raises; it
is a safe boolean probe callers can check before deciding whether to
offer visual generation at all. Every other method raises a typed
ComfyUIClientError on failure for callers that specifically asked for
a result and want to know why it failed.
"""
import time
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("visual")


class ComfyUIClientError(Exception):
    """Raised when a ComfyUI operation that expects a result fails.
    Callers must surface this clearly — never silently fabricate a result."""


class ComfyUIClient(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        """Safe, non-raising probe: True if ComfyUI is reachable right now.
        Always False (never raises) when the integration is disabled."""

    @abstractmethod
    def system_stats(self) -> dict:
        """Return ComfyUI's /system_stats payload. Raises ComfyUIClientError
        if ComfyUI is disabled, unreachable, or returns an error."""

    @abstractmethod
    def submit_workflow(self, graph: dict, client_id: str) -> str:
        """POST /prompt with an already-built, trusted node graph. Returns
        ComfyUI's prompt_id. Raises ComfyUIClientError if ComfyUI is
        disabled/unreachable, or if ComfyUI itself rejects the graph
        (invalid node inputs, missing model file, ...)."""

    @abstractmethod
    def get_queue(self) -> dict:
        """GET /queue — the running and pending prompt queues."""

    @abstractmethod
    def get_history(self, prompt_id: str) -> dict | None:
        """GET /history/{prompt_id}. Returns None if the prompt has not
        completed (or does not exist) yet — that is a normal, expected
        state while polling, not an error."""

    @abstractmethod
    def wait_for_completion(self, prompt_id: str, timeout_seconds: float | None = None) -> dict:
        """Poll get_history until prompt_id appears. Raises
        ComfyUIClientError on timeout — callers must not wait forever."""

    @abstractmethod
    def resolve_output_path(self, subfolder: str, filename: str) -> Path:
        """Resolve a ComfyUI history entry's (subfolder, filename) to a
        local filesystem path under the configured raw output root.
        Raises ComfyUIClientError if the result would escape that root
        (path traversal) or if raw output is not configured."""


class HttpComfyUIClient(ComfyUIClient):
    """Talks to a real local ComfyUI server. This is the ONLY place that
    knows about ComfyUI's HTTP API — see app.ai.llm_service.OllamaLLMService
    for the identical rationale applied to the Ollama integration."""

    def __init__(
        self,
        base_url: str,
        enabled: bool,
        health_check_timeout: float,
        generation_timeout: float = 300.0,
        raw_output_root: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._enabled = enabled
        self._health_check_timeout = health_check_timeout
        self._generation_timeout = generation_timeout
        self._raw_output_root = Path(raw_output_root) if raw_output_root else None

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise ComfyUIClientError("ComfyUI integration is disabled (comfyui_enabled=False).")

    def is_available(self) -> bool:
        if not self._enabled:
            return False
        try:
            response = httpx.get(
                f"{self._base_url}/system_stats", timeout=self._health_check_timeout
            )
            return response.status_code == 200
        except httpx.HTTPError as exc:
            logger.info("ComfyUI health check failed: %s", exc)
            return False

    def _get(self, path: str, timeout: float) -> httpx.Response:
        try:
            response = httpx.get(f"{self._base_url}{path}", timeout=timeout)
            response.raise_for_status()
            return response
        except httpx.ConnectError as exc:
            logger.warning("ComfyUI unreachable: %s", exc)
            raise ComfyUIClientError(f"Could not reach ComfyUI at {self._base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            logger.warning("ComfyUI request timed out: %s", exc)
            raise ComfyUIClientError("ComfyUI took too long to respond.") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("ComfyUI rejected request %s: %s", path, exc)
            raise ComfyUIClientError(f"ComfyUI rejected the request: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning("ComfyUI request failed: %s", exc)
            raise ComfyUIClientError(f"ComfyUI request failed: {exc}") from exc

    def system_stats(self) -> dict:
        self._require_enabled()
        return self._get("/system_stats", self._health_check_timeout).json()

    def submit_workflow(self, graph: dict, client_id: str) -> str:
        self._require_enabled()
        try:
            response = httpx.post(
                f"{self._base_url}/prompt",
                json={"prompt": graph, "client_id": client_id},
                timeout=self._health_check_timeout,
            )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            logger.warning("ComfyUI unreachable: %s", exc)
            raise ComfyUIClientError(f"Could not reach ComfyUI at {self._base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            logger.warning("ComfyUI submit timed out: %s", exc)
            raise ComfyUIClientError("ComfyUI took too long to accept the workflow.") from exc
        except httpx.HTTPError as exc:
            logger.warning("ComfyUI submit failed: %s", exc)
            raise ComfyUIClientError(f"ComfyUI submit failed: {exc}") from exc

        body = response.json()
        if "error" in body:
            raise ComfyUIClientError(f"ComfyUI rejected the workflow: {body['error']}")
        prompt_id = body.get("prompt_id")
        if not prompt_id:
            raise ComfyUIClientError(f"ComfyUI response had no prompt_id: {body}")
        return prompt_id

    def get_queue(self) -> dict:
        self._require_enabled()
        return self._get("/queue", self._health_check_timeout).json()

    def get_history(self, prompt_id: str) -> dict | None:
        self._require_enabled()
        history = self._get(f"/history/{prompt_id}", self._health_check_timeout).json()
        return history.get(prompt_id)

    def wait_for_completion(self, prompt_id: str, timeout_seconds: float | None = None) -> dict:
        self._require_enabled()
        timeout = timeout_seconds if timeout_seconds is not None else self._generation_timeout
        start = time.monotonic()
        while True:
            entry = self.get_history(prompt_id)
            if entry is not None:
                return entry
            if time.monotonic() - start > timeout:
                raise ComfyUIClientError(
                    f"Timed out after {timeout:.0f}s waiting for ComfyUI prompt {prompt_id}."
                )
            time.sleep(1.0)

    def resolve_output_path(self, subfolder: str, filename: str) -> Path:
        if self._raw_output_root is None:
            raise ComfyUIClientError("comfyui_raw_output_root is not configured.")
        candidate = (self._raw_output_root / subfolder / filename).resolve()
        root = self._raw_output_root.resolve()
        if root not in candidate.parents and candidate != root:
            raise ComfyUIClientError(
                f"Refusing to resolve output path outside raw output root: {candidate}"
            )
        return candidate


def build_comfyui_client(settings: Settings | None = None) -> ComfyUIClient:
    settings = settings or get_settings()
    return HttpComfyUIClient(
        base_url=settings.comfyui_base_url,
        enabled=settings.comfyui_enabled,
        health_check_timeout=settings.comfyui_health_check_timeout_seconds,
        generation_timeout=settings.comfyui_generation_timeout_seconds,
        raw_output_root=settings.comfyui_raw_output_root,
    )
