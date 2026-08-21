"""Phase 13L — Conflicts & Politics.

A Conflict is a real, named situation with an actual cause — never
"Organization A hates Organization B because relation=-80." Not a war
simulator: no armies, logistics, or battles simulated here, just the
persistent political fact and its participants. Not tied to exactly two
organizations — INTERNAL_SCHISM may name just one.
"""

from sqlalchemy.orm import Session

from app.core.enums import EventType, OrganizationConflictStatus, OrganizationConflictType
from app.db.models.organization import (
    Organization,
    OrganizationConflict,
    OrganizationConflictParticipant,
)
from app.game.organizations.service import OrganizationError
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


def create_conflict(
    db: Session,
    campaign_id: str,
    name: str,
    *,
    conflict_type: OrganizationConflictType,
    reasons: str,
    participants: list[tuple[Organization, str | None]],
) -> OrganizationConflict:
    """participants is a list of (organization, side_label_or_None) — side
    is an optional free-text label ("attacker"/"defender", or nothing at
    all for a conflict that doesn't split into sides)."""
    if not participants:
        raise OrganizationError("Um conflito precisa de ao menos um participante.")
    if not reasons.strip():
        raise OrganizationError("Um conflito precisa de motivos reais, não apenas uma pontuação.")

    world_minute = get_world_time(db, campaign_id).total_minutes()
    conflict = OrganizationConflict(
        campaign_id=campaign_id,
        name=name,
        conflict_type=conflict_type,
        reasons=reasons,
        status=OrganizationConflictStatus.ACTIVE,
        started_world_minute=world_minute,
    )
    db.add(conflict)
    db.flush()

    for organization, side in participants:
        db.add(
            OrganizationConflictParticipant(
                conflict_id=conflict.id, organization_id=organization.id, side=side
            )
        )
    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.ORGANIZATION_CONFLICT_STARTED,
        actor_type="world",
        payload={
            "conflict_id": conflict.id,
            "conflict_type": conflict_type,
            "participant_ids": [organization.id for organization, _side in participants],
            "reasons": reasons,
        },
        occurred_world_minute=world_minute,
    )
    return conflict


def set_conflict_status(
    db: Session, conflict: OrganizationConflict, new_status: OrganizationConflictStatus
) -> OrganizationConflict:
    if conflict.status == new_status:
        return conflict
    world_minute = get_world_time(db, conflict.campaign_id).total_minutes()
    previous_status = conflict.status
    conflict.status = new_status
    if new_status == OrganizationConflictStatus.RESOLVED:
        conflict.resolved_world_minute = world_minute
    db.flush()

    log_event(
        db,
        conflict.campaign_id,
        EventType.ORGANIZATION_CONFLICT_STATUS_CHANGED,
        actor_type="world",
        payload={
            "conflict_id": conflict.id,
            "previous_status": previous_status,
            "new_status": new_status,
        },
        occurred_world_minute=world_minute,
    )
    return conflict


def conflict_participants(db: Session, conflict_id: str) -> list[Organization]:
    return (
        db.query(Organization)
        .join(
            OrganizationConflictParticipant,
            OrganizationConflictParticipant.organization_id == Organization.id,
        )
        .filter(OrganizationConflictParticipant.conflict_id == conflict_id)
        .all()
    )


def active_conflicts_for_organization(db: Session, organization_id: str) -> list[OrganizationConflict]:
    return (
        db.query(OrganizationConflict)
        .join(
            OrganizationConflictParticipant,
            OrganizationConflictParticipant.conflict_id == OrganizationConflict.id,
        )
        .filter(
            OrganizationConflictParticipant.organization_id == organization_id,
            OrganizationConflict.status == OrganizationConflictStatus.ACTIVE,
        )
        .all()
    )
