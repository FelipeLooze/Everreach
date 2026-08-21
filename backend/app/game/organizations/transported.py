"""Phase 13E — Transported-Created Organizations.

No "CREATE GUILD" button — organization creation emerges from world
action. found_organization_from_group is that action: it requires an
existing, ACTIVE Group (Phase 13A/13B) with real, agency-confirmed
members (nobody is silently drafted — every member got there through
create_group's founding roster or an accepted GroupInvite) and at least
two of them, mirroring "multiple members agreeing." A single character
declaring an organization founded is not enough on its own.

The resulting Organization is always INFORMAL (Phase 13E's own
FORMAL VS INFORMAL section: existence never requires registration) —
formally_recognize_organization is a separate, later, explicit step.

Deferred: this does not (cannot yet) enroll the group's members as
Organization members — that record doesn't exist until Phase 13F's
MEMBERSHIP RECORD. The founding Group's roster remains the authoritative
account of who was there; Phase 13F is what will let the organization
itself track membership going forward.
"""

from sqlalchemy.orm import Session

from app.core.enums import (
    EventType,
    GroupStatus,
    OrganizationFormality,
    OrganizationOrigin,
    OrganizationType,
    OrganizationVisibility,
)
from app.db.models.group import Group
from app.db.models.organization import Organization
from app.game.groups.service import active_group_members
from app.game.organizations.service import OrganizationError, create_organization
from app.game.time.clock import get_world_time
from app.services.event_log import log_event

MIN_FOUNDING_MEMBERS = 2


def found_organization_from_group(
    db: Session,
    group: Group,
    name: str,
    *,
    organization_type: OrganizationType,
    description: str = "",
    visibility: OrganizationVisibility = OrganizationVisibility.PUBLIC,
    headquarters_location_id: str | None = None,
) -> Organization:
    if group.status != GroupStatus.ACTIVE:
        raise OrganizationError(
            f"Só um grupo ativo pode dar origem a uma organização (status atual: {group.status})."
        )
    members = active_group_members(db, group.id)
    if len(members) < MIN_FOUNDING_MEMBERS:
        raise OrganizationError(
            f"Fundar uma organização exige pelo menos {MIN_FOUNDING_MEMBERS} membros reais concordando "
            f"— o grupo tem {len(members)}."
        )

    founder_type = group.leader_type
    founder_id = group.leader_id
    if founder_type is None or founder_id is None:
        founder_type = members[0].member_type
        founder_id = members[0].member_id

    organization = create_organization(
        db,
        group.campaign_id,
        name,
        organization_type=organization_type,
        origin=OrganizationOrigin.TRANSPORTED_CREATED,
        description=description,
        visibility=visibility,
        headquarters_location_id=headquarters_location_id,
        founder_type=founder_type,
        founder_id=founder_id,
    )
    organization.founding_group_id = group.id
    db.flush()

    world_minute = get_world_time(db, group.campaign_id).total_minutes()
    group.status = GroupStatus.COMPLETED_PURPOSE
    db.flush()

    log_event(
        db,
        group.campaign_id,
        EventType.ORGANIZATION_FOUNDED_FROM_GROUP,
        actor_type="group",
        actor_id=group.id,
        payload={
            "organization_id": organization.id,
            "founding_member_ids": [m.member_id for m in members],
        },
        occurred_world_minute=world_minute,
    )
    return organization


def formally_recognize_organization(db: Session, organization: Organization) -> Organization:
    """A later, separate, explicit step — never a prerequisite for the
    organization existing (Phase 13E's FORMAL VS INFORMAL section).
    Deliberately minimal: no registration paperwork/legal system, just
    the state transition itself."""
    if organization.formality == OrganizationFormality.FORMALLY_RECOGNIZED:
        return organization
    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    organization.formality = OrganizationFormality.FORMALLY_RECOGNIZED
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_FORMALLY_RECOGNIZED,
        actor_type="organization",
        actor_id=organization.id,
        payload={},
        occurred_world_minute=world_minute,
    )
    return organization
