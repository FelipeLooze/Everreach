"""Phase 16A — Region Materialization Triggers.

A neighboring Region must not be generated only because the protagonist
reached a map border (spec's "THE PROTAGONIST IS NOT THE ONLY TRIGGER").
Any authoritative system — a simulated character's own travel, an
organization's trade planning, a quest/event, the economy, world
history/Canon — may request that one exist, by calling
request_region_materialization with the matching
RegionMaterializationRequestSource.

This module is deliberately foundation-only (16A). It records that a
neighboring Region is needed and by whom/why; it never generates one.
Actually producing the Region (macro geography, subregions, settlements,
...) is Phase 16I onward, and the physical/political shape of the
boundary itself (barriers, routes, seasonal accessibility) is 16B-16H —
neither exists yet, so nothing here references a "direction" or "border
side." A request is scoped only to its source Region for now; once 16B
introduces boundary sides, the dedup key below can be narrowed to
(campaign, source_region, boundary_side) without changing this contract.
"""

from sqlalchemy.orm import Session

from app.core.enums import EventType, RegionMaterializationRequestStatus
from app.db.models.region import Region
from app.db.models.region_materialization import RegionMaterializationRequest
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


def _require_region_in_campaign(db: Session, campaign_id: str, region_id: str) -> Region:
    region = db.get(Region, region_id)
    if region is None or region.campaign_id != campaign_id:
        raise ValueError(f"Unknown region {region_id} for campaign {campaign_id}")
    return region


def get_pending_region_materialization_request(
    db: Session,
    campaign_id: str,
    source_region_id: str,
) -> RegionMaterializationRequest | None:
    """The one PENDING request (if any) for this source Region."""
    return (
        db.query(RegionMaterializationRequest)
        .filter(
            RegionMaterializationRequest.campaign_id == campaign_id,
            RegionMaterializationRequest.source_region_id == source_region_id,
            RegionMaterializationRequest.status == RegionMaterializationRequestStatus.PENDING,
        )
        .first()
    )


def list_pending_region_materialization_requests(
    db: Session,
    campaign_id: str,
) -> list[RegionMaterializationRequest]:
    return (
        db.query(RegionMaterializationRequest)
        .filter(
            RegionMaterializationRequest.campaign_id == campaign_id,
            RegionMaterializationRequest.status == RegionMaterializationRequestStatus.PENDING,
        )
        .all()
    )


def request_region_materialization(
    db: Session,
    campaign_id: str,
    source_region_id: str,
    requested_by_type: str,
    *,
    requested_by_id: str = "",
    reason: str = "",
) -> RegionMaterializationRequest:
    """
    Record that a Region neighboring source_region_id needs to exist.

    Idempotent: a second call for the same (campaign, source_region) while
    a request is still PENDING returns the existing request unchanged —
    the caller decided a neighbor is needed, not how many times it's been
    asked. This mirrors the exact reuse-existing-pending pattern already
    used for simulated-player arrivals (see
    app.game.players.service.ensure_simulated_player_world_arrival_scheduled).
    """
    _require_region_in_campaign(db, campaign_id, source_region_id)

    existing = get_pending_region_materialization_request(db, campaign_id, source_region_id)
    if existing is not None:
        return existing

    world_minute = get_world_time(db, campaign_id).total_minutes()

    request = RegionMaterializationRequest(
        campaign_id=campaign_id,
        source_region_id=source_region_id,
        requested_by_type=requested_by_type,
        requested_by_id=requested_by_id,
        reason=reason,
        status=RegionMaterializationRequestStatus.PENDING,
        requested_world_minute=world_minute,
    )
    db.add(request)
    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.REGION_MATERIALIZATION_REQUESTED,
        actor_type=requested_by_type,
        actor_id=requested_by_id,
        payload={
            "source_region_id": source_region_id,
            "reason": reason,
        },
        occurred_world_minute=world_minute,
    )

    return request


def mark_region_materialization_request_fulfilled(
    db: Session,
    request_id: str,
    fulfilled_region_id: str,
) -> RegionMaterializationRequest:
    request = db.get(RegionMaterializationRequest, request_id)
    if request is None:
        raise ValueError(f"Unknown region materialization request {request_id}")

    request.status = RegionMaterializationRequestStatus.FULFILLED
    request.fulfilled_region_id = fulfilled_region_id
    db.flush()

    log_event(
        db,
        request.campaign_id,
        EventType.REGION_MATERIALIZATION_FULFILLED,
        actor_type=request.requested_by_type,
        actor_id=request.requested_by_id,
        payload={
            "source_region_id": request.source_region_id,
            "fulfilled_region_id": fulfilled_region_id,
        },
    )

    return request


def mark_region_materialization_request_rejected(
    db: Session,
    request_id: str,
    reason: str = "",
) -> RegionMaterializationRequest:
    request = db.get(RegionMaterializationRequest, request_id)
    if request is None:
        raise ValueError(f"Unknown region materialization request {request_id}")

    request.status = RegionMaterializationRequestStatus.REJECTED
    if reason:
        request.reason = reason
    db.flush()

    log_event(
        db,
        request.campaign_id,
        EventType.REGION_MATERIALIZATION_REJECTED,
        actor_type=request.requested_by_type,
        actor_id=request.requested_by_id,
        payload={
            "source_region_id": request.source_region_id,
            "reason": request.reason,
        },
    )

    return request
