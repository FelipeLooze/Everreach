"""Phase 23D-F — Filesystem Asset Storage."""
import pytest

from app.core.config import Settings
from app.game.visual.asset_storage import (
    VisualAssetStorageError,
    build_asset_directory,
    persist_generated_asset,
    resolve_asset_path,
    stage_reference_image,
)


def _settings(tmp_path) -> Settings:
    return Settings(comfyui_asset_root=str(tmp_path))


def test_build_asset_directory_uses_global_segment_when_campaign_id_is_none(tmp_path):
    settings = _settings(tmp_path)

    directory = build_asset_directory(
        None, "item_definition", "item_sword", "ITEM_ILLUSTRATION", settings=settings
    )

    assert directory == tmp_path / "global" / "item_definition" / "item_sword" / "ITEM_ILLUSTRATION"


def test_build_asset_directory_rejects_a_path_traversal_segment(tmp_path):
    settings = _settings(tmp_path)

    with pytest.raises(VisualAssetStorageError):
        build_asset_directory("campaign_1", "npc", "../../etc", "NPC_PORTRAIT", settings=settings)


def test_persist_generated_asset_copies_the_file_to_an_id_only_name(tmp_path):
    settings = _settings(tmp_path)
    raw_dir = tmp_path / "raw_comfyui_output"
    raw_dir.mkdir()
    raw_file = raw_dir / "ComfyUI_00001_.png"
    raw_file.write_bytes(b"fake-png-bytes")

    relative_path = persist_generated_asset(
        raw_file,
        campaign_id="campaign_1",
        entity_type="npc",
        entity_id="npc_mira",
        asset_type="NPC_PORTRAIT",
        asset_id="vasset_abc123",
        settings=settings,
    )

    assert relative_path == "campaign_1/npc/npc_mira/NPC_PORTRAIT/vasset_abc123.png"
    final_path = tmp_path / relative_path
    assert final_path.is_file()
    assert final_path.read_bytes() == b"fake-png-bytes"
    assert not (final_path.with_suffix(final_path.suffix + ".tmp")).exists()


def test_persist_generated_asset_raises_when_raw_file_is_missing(tmp_path):
    settings = _settings(tmp_path)

    with pytest.raises(VisualAssetStorageError):
        persist_generated_asset(
            tmp_path / "does_not_exist.png",
            campaign_id="campaign_1",
            entity_type="npc",
            entity_id="npc_mira",
            asset_type="NPC_PORTRAIT",
            asset_id="vasset_abc123",
            settings=settings,
        )


def test_persist_generated_asset_rejects_an_unsafe_asset_id(tmp_path):
    settings = _settings(tmp_path)
    raw_file = tmp_path / "raw.png"
    raw_file.write_bytes(b"data")

    with pytest.raises(VisualAssetStorageError):
        persist_generated_asset(
            raw_file,
            campaign_id="campaign_1",
            entity_type="npc",
            entity_id="npc_mira",
            asset_type="NPC_PORTRAIT",
            asset_id="../escape",
            settings=settings,
        )


def test_resolve_asset_path_round_trips_a_persisted_asset(tmp_path):
    settings = _settings(tmp_path)
    raw_file = tmp_path / "raw.png"
    raw_file.write_bytes(b"data")
    relative_path = persist_generated_asset(
        raw_file,
        campaign_id="campaign_1",
        entity_type="npc",
        entity_id="npc_mira",
        asset_type="NPC_PORTRAIT",
        asset_id="vasset_abc123",
        settings=settings,
    )

    resolved = resolve_asset_path(relative_path, settings=settings)

    assert resolved == (tmp_path / relative_path).resolve()
    assert resolved.read_bytes() == b"data"


def test_resolve_asset_path_rejects_path_traversal(tmp_path):
    settings = _settings(tmp_path)

    with pytest.raises(VisualAssetStorageError):
        resolve_asset_path("../../etc/passwd", settings=settings)


def test_resolve_asset_path_requires_configured_root():
    settings = Settings(comfyui_asset_root="")

    with pytest.raises(VisualAssetStorageError):
        resolve_asset_path("campaign_1/npc/npc_mira/NPC_PORTRAIT/vasset_abc123.png", settings=settings)


def _input_settings(tmp_path) -> Settings:
    return Settings(comfyui_input_root=str(tmp_path / "comfy_input"))


def test_stage_reference_image_copies_into_the_input_root_id_only(tmp_path):
    settings = _input_settings(tmp_path)
    source = tmp_path / "source.png"
    source.write_bytes(b"reference-bytes")

    relative = stage_reference_image(source, asset_id="vasset_ref001", settings=settings)

    assert relative == "everreach_reference/vasset_ref001.png"
    staged = tmp_path / "comfy_input" / relative
    assert staged.is_file()
    assert staged.read_bytes() == b"reference-bytes"
    assert not staged.with_suffix(staged.suffix + ".tmp").exists()


def test_stage_reference_image_overwrites_a_stale_previous_copy(tmp_path):
    settings = _input_settings(tmp_path)
    source = tmp_path / "source.png"
    source.write_bytes(b"first-version")
    stage_reference_image(source, asset_id="vasset_ref001", settings=settings)

    source.write_bytes(b"second-version")
    relative = stage_reference_image(source, asset_id="vasset_ref001", settings=settings)

    assert (tmp_path / "comfy_input" / relative).read_bytes() == b"second-version"


def test_stage_reference_image_raises_when_source_is_missing(tmp_path):
    settings = _input_settings(tmp_path)

    with pytest.raises(VisualAssetStorageError):
        stage_reference_image(tmp_path / "does_not_exist.png", asset_id="vasset_ref001", settings=settings)


def test_stage_reference_image_rejects_an_unsafe_asset_id(tmp_path):
    settings = _input_settings(tmp_path)
    source = tmp_path / "source.png"
    source.write_bytes(b"data")

    with pytest.raises(VisualAssetStorageError):
        stage_reference_image(source, asset_id="../escape", settings=settings)


def test_stage_reference_image_requires_configured_input_root(tmp_path):
    settings = Settings(comfyui_input_root="")
    source = tmp_path / "source.png"
    source.write_bytes(b"data")

    with pytest.raises(VisualAssetStorageError):
        stage_reference_image(source, asset_id="vasset_ref001", settings=settings)
