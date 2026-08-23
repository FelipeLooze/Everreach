"""Phase 23D-N / 23D-R.1 — entity-kind dispatch for automatic prompt derivation."""
import pytest
from PIL import Image

from app.core.config import Settings
from app.db.models.npc import NPC
from app.db.models.visual_asset import VisualAsset
from app.game.character.service import create_character
from app.game.inventory.service import add_item, get_or_create_item, list_inventory
from app.game.visual.entity_prompt import (
    UnsupportedGenerationTargetError,
    resolve_generation_inputs,
)
from app.game.visual.npc import NPCVisualIdentityError, set_npc_current_appearance, set_npc_stable_identity
from app.game.visual.npc_reference import NPCReferenceError, set_canonical_reference
from app.game.world.seed import create_campaign, seed_initial_region


def _npc(db_session, campaign_id, region_id, location_id, name="Mira"):
    npc = NPC(campaign_id=campaign_id, region_id=region_id, location_id=location_id, name=name, role="ferreira")
    db_session.add(npc)
    db_session.flush()
    return npc


def _settings(tmp_path) -> Settings:
    return Settings(
        comfyui_asset_root=str(tmp_path / "assets"),
        comfyui_input_root=str(tmp_path / "comfy_input"),
    )


def _reference_asset(campaign_id, npc_id, tmp_path, settings) -> VisualAsset:
    """A real on-disk asset (matching what request_visual_asset would
    have persisted), so resolve_asset_path/stage_reference_image have a
    real file to work with."""
    directory = tmp_path / "assets" / campaign_id / "npc" / npc_id / "NPC_PORTRAIT"
    directory.mkdir(parents=True, exist_ok=True)
    asset_id = "vasset_ref0001"
    Image.new("RGB", (64, 64), color="red").save(directory / f"{asset_id}.png")
    return VisualAsset(
        id=asset_id, campaign_id=campaign_id, entity_type="npc", entity_id=npc_id,
        asset_type="NPC_PORTRAIT",
        storage_path=f"{campaign_id}/npc/{npc_id}/NPC_PORTRAIT/{asset_id}.png",
        mime_type="image/png", width=64, height=64,
        workflow_key="EVERREACH_NPC_PORTRAIT", workflow_version="V1",
        model_identifier="flux-2-klein-4b", seed=1,
    )


# --- TEST 1: no canonical reference -----------------------------------

def test_resolve_generation_inputs_for_npc_portrait_without_reference(db_session):
    campaign = create_campaign(db_session, "Entity Prompt NPC", world_seed=1001)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "silver"})
    db_session.commit()

    workflow_key, workflow_version, prompt_text, seed, reference_image = resolve_generation_inputs(
        db_session, campaign.id, "npc", npc.id, "NPC_PORTRAIT"
    )

    assert workflow_key == "EVERREACH_NPC_PORTRAIT"
    assert workflow_version == "V1"
    assert "silver" in prompt_text
    assert isinstance(seed, int)
    assert reference_image is None


def test_resolve_generation_inputs_raises_for_unknown_npc(db_session):
    campaign = create_campaign(db_session, "Entity Prompt NPC Missing", world_seed=1002)

    with pytest.raises(NPCVisualIdentityError):
        resolve_generation_inputs(db_session, campaign.id, "npc", "npc_does_not_exist", "NPC_PORTRAIT")


def test_resolve_generation_inputs_for_item_illustration(db_session):
    campaign = create_campaign(db_session, "Entity Prompt Item", world_seed=1003)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    get_or_create_item(db_session, "Machado de Ferro", item_type="weapon")
    add_item(db_session, character.id, "Machado de Ferro")
    db_session.commit()
    instance = list_inventory(db_session, character.id)[0]

    workflow_key, workflow_version, prompt_text, seed, reference_image = resolve_generation_inputs(
        db_session, campaign.id, "item_instance", instance.id, "ITEM_ILLUSTRATION"
    )

    assert workflow_key == "EVERREACH_ITEM"
    assert workflow_version == "V3"
    assert prompt_text
    assert isinstance(seed, int)
    assert reference_image is None  # TEST 10 — item behavior unchanged


def test_resolve_generation_inputs_rejects_an_unsupported_combination(db_session):
    campaign = create_campaign(db_session, "Entity Prompt Unsupported", world_seed=1004)

    with pytest.raises(UnsupportedGenerationTargetError):
        resolve_generation_inputs(db_session, campaign.id, "location", "loc_x", "LOCATION_SCENE")


# --- TEST 2: canonical reference exists --------------------------------

def test_resolve_generation_inputs_uses_identity_workflow_when_reference_exists(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Entity Prompt NPC With Reference", world_seed=1005)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "silver", "eye_color": "blue"})
    set_npc_current_appearance(db_session, campaign.id, npc.id, {"clothing": "travel cloak"})
    asset = _reference_asset(campaign.id, npc.id, tmp_path, settings)
    db_session.add(asset)
    db_session.commit()
    set_canonical_reference(db_session, campaign.id, npc.id, asset.id)
    db_session.commit()

    workflow_key, workflow_version, prompt_text, seed, reference_image = resolve_generation_inputs(
        db_session, campaign.id, "npc", npc.id, "NPC_PORTRAIT", settings=settings
    )

    assert workflow_key == "EVERREACH_NPC_IDENTITY"
    assert workflow_version == "V1"
    assert "silver" in prompt_text and "blue" in prompt_text  # stable, preserved
    assert "travel cloak" in prompt_text  # current, depicted
    assert reference_image == "everreach_reference/vasset_ref0001.png"
    staged_path = tmp_path / "comfy_input" / reference_image
    assert staged_path.is_file()


# --- TEST 3: canonical reference != current portrait --------------------

def test_resolve_generation_inputs_uses_canonical_reference_not_current_portrait(db_session, tmp_path):
    """The exact state from the 23D-R live test: Asset A is the
    canonical reference but NOT current; Asset B is current but NOT
    canonical. Dispatch must still resolve Asset A as the reference."""
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Entity Prompt Reference Vs Current", world_seed=1006)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "silver"})
    db_session.commit()

    asset_a = _reference_asset(campaign.id, npc.id, tmp_path, settings)
    db_session.add(asset_a)
    db_session.commit()
    set_canonical_reference(db_session, campaign.id, npc.id, asset_a.id)
    db_session.commit()

    asset_b = VisualAsset(
        id="vasset_current0002", campaign_id=campaign.id, entity_type="npc", entity_id=npc.id,
        asset_type="NPC_PORTRAIT", storage_path="does/not/matter.png", mime_type="image/png",
        width=64, height=64, workflow_key="EVERREACH_NPC_PORTRAIT", workflow_version="V1",
        model_identifier="flux-2-klein-4b", seed=2, is_current=True, is_canonical_reference=False,
    )
    asset_a.is_current = False
    db_session.add(asset_b)
    db_session.commit()

    _wk, _wv, _pt, _seed, reference_image = resolve_generation_inputs(
        db_session, campaign.id, "npc", npc.id, "NPC_PORTRAIT", settings=settings
    )

    assert reference_image == "everreach_reference/vasset_ref0001.png"  # asset_a, not asset_b


# --- TEST 4 (auto-canonicalization) is covered directly against
# service.py in test_visual_service.py — supersede_current_assets never
# touches is_canonical_reference, so nothing here needs to duplicate it.


# --- TEST 5: reference from a different campaign is never used ----------

def test_resolve_generation_inputs_never_uses_another_campaigns_reference(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign_a = create_campaign(db_session, "Entity Prompt Campaign A", world_seed=1007)
    campaign_b = create_campaign(db_session, "Entity Prompt Campaign B", world_seed=1008)
    region_a, village_a = seed_initial_region(db_session, campaign_a.id)
    region_b, village_b = seed_initial_region(db_session, campaign_b.id)
    npc_a = _npc(db_session, campaign_a.id, region_a.id, village_a.id, name="Mira")
    npc_b = _npc(db_session, campaign_b.id, region_b.id, village_b.id, name="Mira")
    set_npc_stable_identity(db_session, campaign_a.id, npc_a.id, {"hair_color": "silver"})
    set_npc_stable_identity(db_session, campaign_b.id, npc_b.id, {"hair_color": "gold"})
    db_session.commit()

    # Only campaign B's NPC gets a canonical reference.
    asset_b = _reference_asset(campaign_b.id, npc_b.id, tmp_path, settings)
    db_session.add(asset_b)
    db_session.commit()
    set_canonical_reference(db_session, campaign_b.id, npc_b.id, asset_b.id)
    db_session.commit()

    workflow_key, _wv, _pt, _seed, reference_image = resolve_generation_inputs(
        db_session, campaign_a.id, "npc", npc_a.id, "NPC_PORTRAIT", settings=settings
    )

    assert workflow_key == "EVERREACH_NPC_PORTRAIT"
    assert reference_image is None


# --- TEST 6: missing reference file fails safely -------------------------

def test_resolve_generation_inputs_fails_safely_when_reference_file_is_missing(db_session, tmp_path):
    settings = _settings(tmp_path)
    campaign = create_campaign(db_session, "Entity Prompt Missing Reference File", world_seed=1009)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "silver"})
    db_session.commit()

    asset = VisualAsset(
        id="vasset_missing0001", campaign_id=campaign.id, entity_type="npc", entity_id=npc.id,
        asset_type="NPC_PORTRAIT", storage_path=f"{campaign.id}/npc/{npc.id}/NPC_PORTRAIT/vasset_missing0001.png",
        mime_type="image/png", width=64, height=64, workflow_key="EVERREACH_NPC_PORTRAIT",
        workflow_version="V1", model_identifier="flux-2-klein-4b", seed=1,
    )
    db_session.add(asset)
    db_session.commit()
    set_canonical_reference(db_session, campaign.id, npc.id, asset.id)
    db_session.commit()
    # Deliberately never write the file to disk.

    with pytest.raises(NPCReferenceError):
        resolve_generation_inputs(db_session, campaign.id, "npc", npc.id, "NPC_PORTRAIT", settings=settings)
