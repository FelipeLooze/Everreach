"""Phase 16S — Transactional Persistence."""

import pytest

from app.core.enums import RegionMaterializationRequestSource, RegionMaterializationRequestStatus
from app.game.world.boundaries import create_regional_boundary
from app.game.world.materialization_orchestrator import fulfill_region_materialization_request
from app.game.world.region_materialization import request_region_materialization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session, world_seed):
    campaign = create_campaign(db_session, f"Orquestracao {world_seed}", world_seed=world_seed)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)
    request = request_region_materialization(
        db_session, campaign.id, source_region.id, RegionMaterializationRequestSource.PLAYER_EXPLORATION,
    )
    return campaign, source_region, boundary, request


def test_fulfilling_a_pending_request_materializes_a_connected_validated_neighbor(db_session):
    campaign, _source, boundary, request = _setup(db_session, 600)

    neighbor = fulfill_region_materialization_request(db_session, request.id, boundary, region_index=1)

    db_session.refresh(request)
    assert request.status == RegionMaterializationRequestStatus.FULFILLED.value
    assert request.fulfilled_region_id == neighbor.id
    assert boundary.destination_region_id == neighbor.id


def test_fulfilling_a_non_pending_request_raises(db_session):
    campaign, _source, boundary, request = _setup(db_session, 601)
    fulfill_region_materialization_request(db_session, request.id, boundary, region_index=1)

    with pytest.raises(ValueError):
        fulfill_region_materialization_request(db_session, request.id, boundary, region_index=2)


def test_fulfilling_with_a_mismatched_boundary_raises(db_session):
    campaign, source_region, _boundary, request = _setup(db_session, 602)
    other_boundary = create_regional_boundary(
        db_session, campaign.id, source_region.id,
        anchor_subregion_id=None,
    )
    # Force a mismatch: pretend this boundary belongs to a different
    # source region than the request was made for.
    other_boundary.source_region_id = "region_somewhere_else"

    with pytest.raises(ValueError):
        fulfill_region_materialization_request(db_session, request.id, other_boundary, region_index=1)


def test_fulfilling_an_unknown_request_raises(db_session):
    _campaign, _source, boundary, _request = _setup(db_session, 603)

    with pytest.raises(ValueError):
        fulfill_region_materialization_request(db_session, "regreq_does_not_exist", boundary, region_index=1)
