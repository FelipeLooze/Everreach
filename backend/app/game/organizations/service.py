"""Phase 13C — Organization Foundation.

Foundation only: the entity itself existing, persistently, independent
of the protagonist. No members (Phase 13F), no roles/reputation/
relationships/goals/resources/actions (13F-13K) — those all build on top
of this without needing a different table per organization type.
"""

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    EventType,
    OrganizationOrigin,
    OrganizationStatus,
    OrganizationType,
    OrganizationVisibility,
    TransportedPeopleStance,
)
from app.db.models.organization import Organization
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


class OrganizationError(Exception):
    pass


def create_organization(
    db: Session,
    campaign_id: str,
    name: str,
    *,
    organization_type: OrganizationType,
    origin: OrganizationOrigin,
    description: str = "",
    visibility: OrganizationVisibility = OrganizationVisibility.PUBLIC,
    headquarters_location_id: str | None = None,
    founder_type: CombatActorType | None = None,
    founder_id: str | None = None,
    transported_people_stance: TransportedPeopleStance | None = None,
) -> Organization:
    """origin (Phase 13D) is always explicit — never a silent default —
    since whether an organization predated transported people is a real
    world fact, not a detail to guess. transported_people_stance is
    per-organization and optional: leave it unset when the world hasn't
    established one yet; never assume every native organization reacts
    to transported people the same way."""
    if not name.strip():
        raise OrganizationError("Uma organização precisa de um nome.")
    world_minute = get_world_time(db, campaign_id).total_minutes()
    organization = Organization(
        campaign_id=campaign_id,
        name=name,
        organization_type=organization_type,
        description=description,
        status=OrganizationStatus.ACTIVE,
        visibility=visibility,
        headquarters_location_id=headquarters_location_id,
        founder_type=founder_type,
        founder_id=founder_id,
        founded_world_minute=world_minute,
        origin=origin,
        transported_people_stance=transported_people_stance,
    )
    db.add(organization)
    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.ORGANIZATION_CREATED,
        actor_type=(founder_type.lower() if founder_type else "world"),
        actor_id=founder_id or "",
        payload={"organization_id": organization.id, "organization_type": organization_type},
        occurred_world_minute=world_minute,
    )
    return organization


def set_organization_status(
    db: Session, organization: Organization, new_status: OrganizationStatus
) -> Organization:
    """A generic lifecycle transition. History is never deleted — an
    organization that stops functioning still existed; its row stays,
    only its status changes."""
    if organization.status == new_status:
        return organization
    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    previous_status = organization.status
    organization.status = new_status
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_STATUS_CHANGED,
        actor_type="organization",
        actor_id=organization.id,
        payload={"previous_status": previous_status, "new_status": new_status},
        occurred_world_minute=world_minute,
    )
    return organization
