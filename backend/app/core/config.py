from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./everreach.db"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "hermes3:8b-llama3.1-q4_K_M"
    ollama_timeout_seconds: float = 180.0
    # Phase 18H — a small dedicated embedding model, separate from the
    # narration/intent model above. None disables semantic retrieval
    # gracefully (app.ai.retrieval.semantic degrades to no candidates)
    # rather than requiring every local setup to have one pulled.
    ollama_embedding_model: str | None = "nomic-embed-text"

    log_level: str = "INFO"

    cors_origins: list[str] = ["http://localhost:5173"]

    # Phase 23D-B — ComfyUI is an optional local integration (see
    # app.game.visual.comfyui_client): disabled by default so a fresh
    # checkout / CI never tries to reach a local GPU server. When
    # enabled, only base_url and a short health-check timeout are
    # needed yet — asset/workflow root paths are reserved for later
    # subphases (23D-C/F) and intentionally not read here yet.
    comfyui_enabled: bool = False
    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_health_check_timeout_seconds: float = 5.0
    # Cold model load from the HDD alone has been observed to take ~2
    # minutes (Phase 23B/23C); this must stay generous, never a short
    # "reasonable API" timeout, or every first generation after a
    # ComfyUI restart would spuriously time out.
    comfyui_generation_timeout_seconds: float = 300.0
    # ComfyUI and the Everreach backend run on the same machine, so raw
    # output is read directly off disk rather than downloaded over
    # HTTP (GET /view) — this is where ComfyUI's own SaveImage nodes
    # write to (see E:\RPG\start_comfyui.bat's --base-directory).
    comfyui_raw_output_root: str = ""
    # Phase 23D-C — where app.game.visual.workflow_registry reads the
    # trusted, hand-approved API-format workflow JSON files from (the
    # E:\RPG\Workflows\api output of Phase 23B/23C's own generation
    # scripts). The registry's own allowlist decides which filenames are
    # ever loaded from here — this path alone does not grant trust.
    comfyui_workflow_root: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
