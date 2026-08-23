from functools import lru_cache

from app.game.visual.comfyui_client import ComfyUIClient, build_comfyui_client

_override: ComfyUIClient | None = None


def set_comfyui_client_override(client: ComfyUIClient | None) -> None:
    """Test hook: inject a fake ComfyUIClient instead of talking to a real server."""
    global _override
    _override = client


@lru_cache
def _cached_default() -> ComfyUIClient:
    return build_comfyui_client()


def get_comfyui_client() -> ComfyUIClient:
    if _override is not None:
        return _override
    return _cached_default()
