"""Phase 23D-K — Deduplication & Reuse."""
from app.core.enums import VisualGenerationRequestStatus
from app.db.models.visual_asset import VisualAsset
from app.game.visual.dedup import (
    compute_spec_fingerprint,
    find_in_flight_request,
    find_reusable_asset,
)
from app.game.visual.generation_request import create_request, mark_completed, mark_in_progress
from app.game.world.seed import create_campaign


def test_compute_spec_fingerprint_is_stable_for_identical_inputs():
    kwargs = dict(
        prompt_text="a prompt", workflow_key="EVERREACH_ITEM", workflow_version="V3", seed=5001,
    )
    assert compute_spec_fingerprint(**kwargs) == compute_spec_fingerprint(**kwargs)


def test_compute_spec_fingerprint_changes_when_prompt_text_changes():
    base = compute_spec_fingerprint(
        prompt_text="a prompt", workflow_key="EVERREACH_ITEM", workflow_version="V3", seed=5001,
    )
    changed = compute_spec_fingerprint(
        prompt_text="a different prompt", workflow_key="EVERREACH_ITEM", workflow_version="V3", seed=5001,
    )
    assert base != changed


def test_compute_spec_fingerprint_changes_when_reference_image_changes():
    base = compute_spec_fingerprint(
        prompt_text="edit it", workflow_key="EVERREACH_NPC_IDENTITY", workflow_version="V1",
        seed=5101, reference_image="canonical_v1.png",
    )
    changed = compute_spec_fingerprint(
        prompt_text="edit it", workflow_key="EVERREACH_NPC_IDENTITY", workflow_version="V1",
        seed=5101, reference_image="canonical_v2.png",
    )
    assert base != changed


def _create(db_session, campaign_id, **overrides):
    params = dict(
        entity_type="npc", entity_id="npc_mira", asset_type="NPC_PORTRAIT",
        workflow_key="EVERREACH_NPC_PORTRAIT", workflow_version="V1", campaign_id=campaign_id, seed=1,
    )
    params.update(overrides)
    return create_request(db_session, **params)


def test_find_in_flight_request_is_none_when_nothing_is_pending(db_session):
    campaign = create_campaign(db_session, "Dedup No In Flight", world_seed=701)

    assert find_in_flight_request(db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT") is None


def test_find_in_flight_request_finds_a_pending_request(db_session):
    campaign = create_campaign(db_session, "Dedup Pending", world_seed=702)
    request = _create(db_session, campaign.id)
    db_session.commit()

    found = find_in_flight_request(db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT")

    assert found.id == request.id


def test_find_in_flight_request_finds_an_in_progress_request(db_session):
    campaign = create_campaign(db_session, "Dedup In Progress", world_seed=703)
    request = _create(db_session, campaign.id)
    mark_in_progress(db_session, request.id)
    db_session.commit()

    found = find_in_flight_request(db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT")

    assert found.id == request.id


def test_find_in_flight_request_ignores_completed_requests(db_session):
    campaign = create_campaign(db_session, "Dedup Completed Not In Flight", world_seed=704)
    request = _create(db_session, campaign.id)
    mark_completed(db_session, request.id, "vasset_x")
    db_session.commit()

    assert find_in_flight_request(db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT") is None


def test_find_in_flight_request_is_scoped_to_entity_and_asset_type(db_session):
    campaign = create_campaign(db_session, "Dedup Scoped", world_seed=705)
    _create(db_session, campaign.id, entity_id="npc_logan")
    db_session.commit()

    assert find_in_flight_request(db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT") is None


def _asset(campaign_id, **overrides) -> VisualAsset:
    params = dict(
        campaign_id=campaign_id, entity_type="npc", entity_id="npc_mira", asset_type="NPC_PORTRAIT",
        storage_path="npcs/npc_mira/NPC_PORTRAIT/vasset_x.png", mime_type="image/png",
        width=1024, height=1024, workflow_key="EVERREACH_NPC_PORTRAIT", workflow_version="V1",
        model_identifier="flux-2-klein-4b", seed=1, spec_fingerprint="fp-1",
    )
    params.update(overrides)
    return VisualAsset(**params)


def test_find_reusable_asset_matches_on_fingerprint(db_session):
    campaign = create_campaign(db_session, "Dedup Reusable Match", world_seed=706)
    asset = _asset(campaign.id)
    db_session.add(asset)
    db_session.commit()

    found = find_reusable_asset(db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT", "fp-1")

    assert found.id == asset.id


def test_find_reusable_asset_is_none_for_a_different_fingerprint(db_session):
    campaign = create_campaign(db_session, "Dedup Reusable Mismatch", world_seed=707)
    db_session.add(_asset(campaign.id, spec_fingerprint="fp-1"))
    db_session.commit()

    assert find_reusable_asset(db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT", "fp-2") is None


def test_find_reusable_asset_ignores_superseded_assets(db_session):
    campaign = create_campaign(db_session, "Dedup Reusable Superseded", world_seed=708)
    db_session.add(_asset(campaign.id, spec_fingerprint="fp-1", is_current=False))
    db_session.commit()

    assert find_reusable_asset(db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT", "fp-1") is None
