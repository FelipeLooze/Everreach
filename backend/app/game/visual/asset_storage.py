"""Phase 23D-F — Filesystem Asset Storage.

Copies an accepted raw ComfyUI generation output into the PERSISTENT
Everreach asset store (comfyui_asset_root) — never mixing it up with
ComfyUI's own raw output directory (comfyui_raw_output_root, owned by
app.game.visual.comfyui_client). ComfyUI's raw output is disposable
scratch space; only what this module deliberately copies out of it
becomes a durable, ID-addressed VisualAsset file.

Every path segment this module builds is either a fixed literal
("global") or a value the caller already validated as a real entity/
asset-type/asset id (never raw user text) — but every segment is still
checked for path-traversal characters here too, as the one place that
actually turns those values into filesystem paths, mirroring
ComfyUIClient.resolve_output_path's own "belt and suspenders" stance on
its own raw-output root.

Filenames are ID-only (asset_id + the source file's original
extension) — never the original ComfyUI filename, never anything
derived from a prompt or NPC name — so a stored asset can never leak
what it depicts through its own path.
"""
import os
import shutil
from pathlib import Path

from app.core.config import Settings, get_settings


class VisualAssetStorageError(Exception):
    """Raised for any asset-storage failure: missing raw file, an unsafe
    path segment, or a resolved path that would escape the asset root."""


def _root(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    if not settings.comfyui_asset_root:
        raise VisualAssetStorageError("comfyui_asset_root is not configured.")
    return Path(settings.comfyui_asset_root)


def _validate_path_segment(segment: str) -> None:
    if not segment:
        raise VisualAssetStorageError("Path segment must not be empty.")
    if segment in (".", ".."):
        raise VisualAssetStorageError(f"Unsafe path segment: {segment!r}")
    if "/" in segment or "\\" in segment:
        raise VisualAssetStorageError(f"Path segment must not contain a path separator: {segment!r}")


def build_asset_directory(
    campaign_id: str | None,
    entity_type: str,
    entity_id: str,
    asset_type: str,
    *,
    settings: Settings | None = None,
) -> Path:
    """The directory a given entity/asset_type's assets live under.
    campaign_id=None (a campaign-global entity, e.g. an ItemDefinition)
    is stored under a literal "global" segment rather than a blank one."""
    campaign_segment = campaign_id if campaign_id else "global"
    for segment in (campaign_segment, entity_type, entity_id, asset_type):
        _validate_path_segment(segment)
    return _root(settings) / campaign_segment / entity_type / entity_id / asset_type


def persist_generated_asset(
    raw_path: Path,
    *,
    campaign_id: str | None,
    entity_type: str,
    entity_id: str,
    asset_type: str,
    asset_id: str,
    settings: Settings | None = None,
) -> str:
    """Copy an accepted raw generation output into the persistent asset
    store and return its path RELATIVE to comfyui_asset_root (what
    VisualAsset.storage_path should hold — never an absolute filesystem
    path, so it stays portable and safe to resolve later via
    resolve_asset_path).

    Writes to a sibling ".tmp" file first and then atomically renames it
    into place (os.replace), so a reader can never observe a partially
    copied file at the final name — the same "no torn writes" guarantee
    ComfyUI's own generation directly needs.
    """
    settings = settings or get_settings()
    if not raw_path.is_file():
        raise VisualAssetStorageError(f"Raw generated file not found: {raw_path}")
    _validate_path_segment(asset_id)

    directory = build_asset_directory(
        campaign_id, entity_type, entity_id, asset_type, settings=settings
    )
    directory.mkdir(parents=True, exist_ok=True)

    extension = raw_path.suffix
    final_path = directory / f"{asset_id}{extension}"
    temp_path = directory / f"{asset_id}{extension}.tmp"

    shutil.copyfile(raw_path, temp_path)
    os.replace(temp_path, final_path)

    return final_path.relative_to(_root(settings)).as_posix()


def resolve_asset_path(storage_path: str, *, settings: Settings | None = None) -> Path:
    """Resolve a VisualAsset.storage_path back to an absolute filesystem
    path. Raises if the result would escape comfyui_asset_root."""
    root = _root(settings).resolve()
    candidate = (root / storage_path).resolve()
    if root not in candidate.parents and candidate != root:
        raise VisualAssetStorageError(
            f"Refusing to resolve asset path outside asset root: {candidate}"
        )
    return candidate


def _input_root(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    if not settings.comfyui_input_root:
        raise VisualAssetStorageError("comfyui_input_root is not configured.")
    return Path(settings.comfyui_input_root)


def stage_reference_image(
    source_path: Path, *, asset_id: str, settings: Settings | None = None
) -> str:
    """Phase 23D-R.1 — copy an already-resolved, trusted local file (a
    canonical NPC reference's own asset file, already validated by
    resolve_asset_path) into ComfyUI's OWN input directory, and return
    the value its LoadImage node's "image" input should be set to.

    ComfyUI's LoadImage resolves an "image" value with no [input]/
    [output]/[temp] suffix against its own input directory ONLY
    (confirmed by reading ComfyUI's folder_paths.get_annotated_filepath)
    — an absolute Everreach asset path can never reach it directly, and
    ComfyUI's own traversal guard (is_within_directory) would reject one
    anyway. The staged filename is always ID-based
    (everreach_reference/<asset_id><ext>) — never derived from an NPC
    name or anything else caller-controlled — mirroring
    persist_generated_asset's own "IDs only" filename discipline.

    Always copies fresh (no "already staged" shortcut): these are small
    PNGs, and a stale copy from a since-superseded reference would be a
    much worse failure mode than a redundant copy.
    """
    settings = settings or get_settings()
    if not source_path.is_file():
        raise VisualAssetStorageError(f"Reference source file not found: {source_path}")
    _validate_path_segment(asset_id)

    directory = _input_root(settings) / "everreach_reference"
    directory.mkdir(parents=True, exist_ok=True)

    extension = source_path.suffix
    final_path = directory / f"{asset_id}{extension}"
    temp_path = directory / f"{asset_id}{extension}.tmp"

    shutil.copyfile(source_path, temp_path)
    os.replace(temp_path, final_path)

    return f"everreach_reference/{asset_id}{extension}"
