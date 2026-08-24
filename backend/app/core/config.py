from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./everreach.db"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "hermes3:8b-llama3.1-q4_K_M"
    ollama_timeout_seconds: float = 180.0
    # Phase 24A.1 — verified live against the installed Ollama server
    # that options.num_predict is respected (a real cap, not a guess:
    # requesting num_predict=30 returned exactly eval_count=30 with
    # done_reason="length"). Without any cap, generation has no upper
    # bound at all, which is part of how the model was able to keep
    # going into a fabricated multi-turn "PLAYER:/NARRATOR:" scaffold
    # instead of stopping after one coherent beat. 500 gives generous
    # room for narrator.py's own "no máximo dois/três parágrafos
    # curtos" style guidance (a genuinely long reply needs nowhere
    # near this many tokens) while still cutting off a runaway
    # continuation well before it can simulate several more turns.
    ollama_num_predict: int = 500
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
    # Phase 23D-F — root of the PERSISTENT Everreach asset store (never
    # ComfyUI's own raw output directory, comfyui_raw_output_root above).
    # app.game.visual.asset_storage copies an accepted raw generation
    # into <this root>/<campaign or "global">/<entity_type>/<entity_id>/
    # <asset_type>/<asset_id><ext> and never anywhere else.
    comfyui_asset_root: str = ""
    # Phase 23D-R.1 — ComfyUI's own LoadImage node resolves an "image"
    # value with no [input]/[output]/[temp] suffix against ITS OWN input
    # directory only (confirmed by reading ComfyUI's folder_paths.py:
    # get_annotated_filepath defaults to get_input_directory(), and its
    # own is_within_directory traversal guard means an absolute Everreach
    # asset path can never resolve there directly). A canonical NPC
    # reference must be staged (copied) into this directory before a
    # reference-based generation can use it — see
    # app.game.visual.asset_storage.stage_reference_image.
    comfyui_input_root: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
