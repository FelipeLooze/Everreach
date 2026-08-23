"""Phase 23D-N — Visual Asset Service API.

These tests deliberately do NOT wire up a real (or tmp_path-backed)
ComfyUI/workflow/asset filesystem — that full generation pipeline is
already thoroughly covered at the service layer (app/tests/
test_visual_service.py, with explicit Settings overrides). What this
route adds on top is HTTP plumbing, entity-kind dispatch, and campaign
scoping, which is exactly what these tests exercise: an
_AlwaysOfflineClient is injected via the same DI override every other
ComfyUI-adjacent test uses, so a "failed generation" path is exercised
deterministically rather than depending on whatever COMFYUI_ENABLED
happens to be in the machine's own .env. A failed generation must still
be a 200 response, never a 5xx ("COMFYUI FAILURE != GAMEPLAY FAILURE",
spec) — that is exactly what these assert.
"""
import pytest

from app.api.dependencies.comfyui import set_comfyui_client_override
from app.db.models.npc import NPC
from app.db.models.visual_asset import VisualAsset
from app.game.visual.comfyui_client import ComfyUIClient
from app.game.visual.generation_request import create_request, mark_failed
from app.game.visual.npc import set_npc_stable_identity
from app.game.world.seed import create_campaign, seed_initial_region


@pytest.fixture(autouse=True)
def _reset_comfyui_override():
    yield
    set_comfyui_client_override(None)


class _AlwaysOfflineClient(ComfyUIClient):
    def is_available(self) -> bool:
        return False

    def system_stats(self) -> dict:
        return {}

    def submit_workflow(self, graph, client_id):
        raise AssertionError("should never submit while offline")

    def get_queue(self) -> dict:
        return {}

    def get_history(self, prompt_id):
        return None

    def wait_for_completion(self, prompt_id, timeout_seconds=None):
        raise AssertionError("should never wait while offline")

    def resolve_output_path(self, subfolder, filename):
        raise AssertionError("should never resolve output while offline")


def _npc(db_session, campaign_id, region_id, location_id, name="Mira"):
    npc = NPC(campaign_id=campaign_id, region_id=region_id, location_id=location_id, name=name, role="ferreira")
    db_session.add(npc)
    db_session.flush()
    return npc


def test_generate_returns_200_with_a_failed_request_when_comfyui_is_offline(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Offline", world_seed=1101)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "silver"})
    db_session.commit()
    set_comfyui_client_override(_AlwaysOfflineClient())

    response = client.post(
        f"/api/campaigns/{campaign.id}/visual-assets/generate",
        json={"entity_type": "npc", "entity_id": npc.id, "asset_type": "NPC_PORTRAIT"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["error_code"] == "COMFYUI_OFFLINE"
    assert body["result_asset_id"] is None


def test_generate_returns_400_for_an_unsupported_entity_asset_combination(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Unsupported", world_seed=1102)
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign.id}/visual-assets/generate",
        json={"entity_type": "location", "entity_id": "loc_x", "asset_type": "LOCATION_SCENE"},
    )

    assert response.status_code == 400


def test_generate_returns_404_for_an_unknown_npc(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Unknown NPC", world_seed=1103)
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign.id}/visual-assets/generate",
        json={"entity_type": "npc", "entity_id": "npc_does_not_exist", "asset_type": "NPC_PORTRAIT"},
    )

    assert response.status_code == 404


def test_generate_returns_404_for_an_unknown_campaign(client, db_session):
    response = client.post(
        "/api/campaigns/campaign_does_not_exist/visual-assets/generate",
        json={"entity_type": "npc", "entity_id": "npc_x", "asset_type": "NPC_PORTRAIT"},
    )

    assert response.status_code == 404


def test_get_generation_request_status(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Request Status", world_seed=1104)
    request = create_request(
        db_session, entity_type="npc", entity_id="npc_x", asset_type="NPC_PORTRAIT",
        workflow_key="EVERREACH_NPC_PORTRAIT", workflow_version="V1", campaign_id=campaign.id, seed=1,
    )
    db_session.commit()

    response = client.get(f"/api/campaigns/{campaign.id}/visual-assets/requests/{request.id}")

    assert response.status_code == 200
    assert response.json()["id"] == request.id
    assert response.json()["status"] == "PENDING"


def test_get_generation_request_status_404_for_unknown_request(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Request Unknown", world_seed=1105)
    db_session.commit()

    response = client.get(f"/api/campaigns/{campaign.id}/visual-assets/requests/vgen_does_not_exist")

    assert response.status_code == 404


def test_get_generation_request_status_404_for_wrong_campaign(client, db_session):
    campaign_a = create_campaign(db_session, "Visual Route Wrong Campaign A", world_seed=1106)
    campaign_b = create_campaign(db_session, "Visual Route Wrong Campaign B", world_seed=1107)
    request = create_request(
        db_session, entity_type="npc", entity_id="npc_x", asset_type="NPC_PORTRAIT",
        workflow_key="EVERREACH_NPC_PORTRAIT", workflow_version="V1", campaign_id=campaign_a.id, seed=1,
    )
    db_session.commit()

    response = client.get(f"/api/campaigns/{campaign_b.id}/visual-assets/requests/{request.id}")

    assert response.status_code == 404


def test_retry_returns_a_new_failed_request_when_still_offline(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Retry", world_seed=1108)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "silver"})
    failed_request = create_request(
        db_session, entity_type="npc", entity_id=npc.id, asset_type="NPC_PORTRAIT",
        workflow_key="EVERREACH_NPC_PORTRAIT", workflow_version="V1", campaign_id=campaign.id, seed=1,
    )
    mark_failed(db_session, failed_request.id, "COMFYUI_OFFLINE", "was offline")
    db_session.commit()
    set_comfyui_client_override(_AlwaysOfflineClient())

    response = client.post(
        f"/api/campaigns/{campaign.id}/visual-assets/requests/{failed_request.id}/retry"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] != failed_request.id
    assert body["status"] == "FAILED"
    assert body["error_code"] == "COMFYUI_OFFLINE"


def test_retry_returns_409_for_a_non_retryable_request(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Retry Not Allowed", world_seed=1109)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "silver"})
    failed_request = create_request(
        db_session, entity_type="npc", entity_id=npc.id, asset_type="NPC_PORTRAIT",
        workflow_key="EVERREACH_NPC_PORTRAIT", workflow_version="V1", campaign_id=campaign.id, seed=1,
    )
    mark_failed(db_session, failed_request.id, "COMFYUI_REJECTED_WORKFLOW", "bad graph")
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign.id}/visual-assets/requests/{failed_request.id}/retry"
    )

    assert response.status_code == 409


def _asset(campaign_id, **overrides) -> VisualAsset:
    params = dict(
        campaign_id=campaign_id, entity_type="npc", entity_id="npc_mira", asset_type="NPC_PORTRAIT",
        storage_path="npcs/npc_mira/NPC_PORTRAIT/vasset_x.png", mime_type="image/png",
        width=1024, height=1024, workflow_key="EVERREACH_NPC_PORTRAIT", workflow_version="V1",
        model_identifier="flux-2-klein-4b", seed=1,
    )
    params.update(overrides)
    return VisualAsset(**params)


def test_get_current_visual_asset(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Current Asset", world_seed=1110)
    asset = _asset(campaign.id)
    db_session.add(asset)
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/visual-assets/current",
        params={"entity_type": "npc", "entity_id": "npc_mira", "asset_type": "NPC_PORTRAIT"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == asset.id


def test_get_current_visual_asset_404_when_none_exists(client, db_session):
    campaign = create_campaign(db_session, "Visual Route No Current Asset", world_seed=1111)
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/visual-assets/current",
        params={"entity_type": "npc", "entity_id": "npc_mira", "asset_type": "NPC_PORTRAIT"},
    )

    assert response.status_code == 404


def test_validate_visual_asset_marks_valid(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Validate Valid", world_seed=1112)
    asset = _asset(campaign.id)
    db_session.add(asset)
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign.id}/visual-assets/{asset.id}/validate",
        json={"status": "VALID"},
    )

    assert response.status_code == 200
    assert response.json()["validation_status"] == "VALID"
    assert response.json()["is_current"] is True


def test_validate_visual_asset_marks_invalid_and_clears_is_current(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Validate Invalid", world_seed=1113)
    asset = _asset(campaign.id, is_current=True)
    db_session.add(asset)
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign.id}/visual-assets/{asset.id}/validate",
        json={"status": "INVALID"},
    )

    assert response.status_code == 200
    assert response.json()["validation_status"] == "INVALID"
    assert response.json()["is_current"] is False


def test_validate_visual_asset_422_for_unknown_status_value(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Validate Bad Status", world_seed=1114)
    asset = _asset(campaign.id)
    db_session.add(asset)
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign.id}/visual-assets/{asset.id}/validate",
        json={"status": "SUPER_VALID"},
    )

    assert response.status_code == 422


def test_validate_visual_asset_404_for_unknown_asset(client, db_session):
    campaign = create_campaign(db_session, "Visual Route Validate Unknown Asset", world_seed=1115)
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign.id}/visual-assets/vasset_does_not_exist/validate",
        json={"status": "VALID"},
    )

    assert response.status_code == 404


def test_validate_visual_asset_404_for_wrong_campaign(client, db_session):
    campaign_a = create_campaign(db_session, "Visual Route Validate Campaign A", world_seed=1116)
    campaign_b = create_campaign(db_session, "Visual Route Validate Campaign B", world_seed=1117)
    asset = _asset(campaign_a.id)
    db_session.add(asset)
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign_b.id}/visual-assets/{asset.id}/validate",
        json={"status": "VALID"},
    )

    assert response.status_code == 404
