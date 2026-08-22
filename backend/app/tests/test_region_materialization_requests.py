"""Phase 16A — Region Materialization Triggers.

request_region_materialization is the one authoritative entry point any
system (player exploration, a simulated character, an organization, a
quest/event, the economy, world history/Canon) uses to record that a
neighboring Region needs to exist. It never generates a Region itself —
that arrives in a later subphase (16I+).
"""

import pytest

from app.core.enums import (
    EventType,
    RegionMaterializationRequestSource,
    RegionMaterializationRequestStatus,
)
from app.db.models.event import WorldEvent
from app.db.models.region import Region
from app.db.models.region_materialization import RegionMaterializationRequest
from app.game.world.region_materialization import (
    get_pending_region_materialization_request,
    list_pending_region_materialization_requests,
    mark_region_materialization_request_fulfilled,
    mark_region_materialization_request_rejected,
    request_region_materialization,
)
from app.game.world.seed import create_campaign, seed_initial_region


def test_request_creates_a_pending_request_and_logs_an_event(db_session):
    campaign = create_campaign(db_session, "Fronteira Leste")
    region, _village = seed_initial_region(db_session, campaign.id)

    request = request_region_materialization(
        db_session,
        campaign.id,
        region.id,
        RegionMaterializationRequestSource.PLAYER_EXPLORATION,
        requested_by_id="char_logan",
        reason="Logan approached the eastern frontier.",
    )

    assert request.status == RegionMaterializationRequestStatus.PENDING
    assert request.source_region_id == region.id
    assert request.requested_by_type == RegionMaterializationRequestSource.PLAYER_EXPLORATION
    assert request.fulfilled_region_id is None

    event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type == EventType.REGION_MATERIALIZATION_REQUESTED.value,
        )
        .one()
    )
    assert event.actor_id == "char_logan"


def test_every_spec_source_category_can_request_materialization(db_session):
    campaign = create_campaign(db_session, "Todas As Fontes")
    region, _village = seed_initial_region(db_session, campaign.id)

    for source in RegionMaterializationRequestSource:
        db_session.query(RegionMaterializationRequest).delete()
        db_session.flush()

        request = request_region_materialization(
            db_session,
            campaign.id,
            region.id,
            source,
            reason=f"triggered by {source.value}",
        )
        assert request.requested_by_type == source.value


def test_duplicate_requests_for_the_same_source_region_collapse_to_one(db_session):
    campaign = create_campaign(db_session, "Pedidos Duplicados")
    region, _village = seed_initial_region(db_session, campaign.id)

    first = request_region_materialization(
        db_session,
        campaign.id,
        region.id,
        RegionMaterializationRequestSource.SIMULATED_CHARACTER,
        requested_by_id="simp_mira",
        reason="Mira travels toward the eastern frontier.",
    )

    second = request_region_materialization(
        db_session,
        campaign.id,
        region.id,
        RegionMaterializationRequestSource.ORGANIZATION,
        requested_by_id="org_merchants",
        reason="A merchant organization plans trade with distant territory.",
    )

    assert second.id == first.id
    assert second.requested_by_type == RegionMaterializationRequestSource.SIMULATED_CHARACTER

    all_requests = (
        db_session.query(RegionMaterializationRequest)
        .filter(RegionMaterializationRequest.campaign_id == campaign.id)
        .all()
    )
    assert len(all_requests) == 1

    events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type == EventType.REGION_MATERIALIZATION_REQUESTED.value,
        )
        .all()
    )
    assert len(events) == 1


def test_request_for_unknown_region_raises(db_session):
    campaign = create_campaign(db_session, "Regiao Invalida")

    with pytest.raises(ValueError):
        request_region_materialization(
            db_session,
            campaign.id,
            "region_does_not_exist",
            RegionMaterializationRequestSource.ECONOMY,
        )


def test_pending_lookup_helpers(db_session):
    campaign = create_campaign(db_session, "Consulta De Pendentes")
    region, _village = seed_initial_region(db_session, campaign.id)

    assert get_pending_region_materialization_request(db_session, campaign.id, region.id) is None
    assert list_pending_region_materialization_requests(db_session, campaign.id) == []

    request = request_region_materialization(
        db_session,
        campaign.id,
        region.id,
        RegionMaterializationRequestSource.WORLD_HISTORY,
        reason="Existing Canon references people beyond current materialization.",
    )

    assert get_pending_region_materialization_request(db_session, campaign.id, region.id).id == request.id
    pending = list_pending_region_materialization_requests(db_session, campaign.id)
    assert [r.id for r in pending] == [request.id]


def test_fulfilling_a_request_allows_a_fresh_request_afterward(db_session):
    campaign = create_campaign(db_session, "Cumprido")
    region, _village = seed_initial_region(db_session, campaign.id)

    request = request_region_materialization(
        db_session,
        campaign.id,
        region.id,
        RegionMaterializationRequestSource.MILITARY_POLITICAL,
        reason="A conflict references a neighboring Region.",
    )

    neighbor_region = Region(campaign_id=campaign.id, name="Terras Orientais")
    db_session.add(neighbor_region)
    db_session.flush()

    fulfilled = mark_region_materialization_request_fulfilled(
        db_session,
        request.id,
        neighbor_region.id,
    )

    assert fulfilled.status == RegionMaterializationRequestStatus.FULFILLED
    assert fulfilled.fulfilled_region_id == neighbor_region.id
    assert get_pending_region_materialization_request(db_session, campaign.id, region.id) is None

    fulfilled_event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type == EventType.REGION_MATERIALIZATION_FULFILLED.value,
        )
        .one()
    )
    assert fulfilled_event is not None

    second = request_region_materialization(
        db_session,
        campaign.id,
        region.id,
        RegionMaterializationRequestSource.QUEST_EVENT,
        reason="A real world event requires a distant territory.",
    )
    assert second.id != request.id
    assert second.status == RegionMaterializationRequestStatus.PENDING


def test_rejecting_a_request_allows_a_fresh_request_afterward(db_session):
    campaign = create_campaign(db_session, "Rejeitado")
    region, _village = seed_initial_region(db_session, campaign.id)

    request = request_region_materialization(
        db_session,
        campaign.id,
        region.id,
        RegionMaterializationRequestSource.ECONOMY,
        reason="A major imported resource requires an external origin.",
    )

    rejected = mark_region_materialization_request_rejected(
        db_session,
        request.id,
        reason="Validation failed: border facts were inconsistent.",
    )

    assert rejected.status == RegionMaterializationRequestStatus.REJECTED
    assert rejected.reason == "Validation failed: border facts were inconsistent."
    assert get_pending_region_materialization_request(db_session, campaign.id, region.id) is None

    rejected_event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type == EventType.REGION_MATERIALIZATION_REJECTED.value,
        )
        .one()
    )
    assert rejected_event is not None

    second = request_region_materialization(
        db_session,
        campaign.id,
        region.id,
        RegionMaterializationRequestSource.ECONOMY,
        reason="A major imported resource requires an external origin.",
    )
    assert second.id != request.id
