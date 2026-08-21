"""Phase 13H — Organization Relationships.

Not one exclusive enum per pair: multiple OrganizationRelation rows of
different relation_type may coexist and be ACTIVE at once between the
same two organizations — a merchant guild may be a rival's TRADE_PARTNER
and COMPETITOR simultaneously. A relation's reason and history are never
collapsed into a bare number; ending one never deletes it.
"""

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.enums import EventType, OrganizationRelationStatus, OrganizationRelationType
from app.db.models.organization import Organization, OrganizationRelation
from app.game.organizations.service import OrganizationError
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


def _pair_filter(organization_a_id: str, organization_b_id: str):
    return or_(
        (OrganizationRelation.organization_a_id == organization_a_id)
        & (OrganizationRelation.organization_b_id == organization_b_id),
        (OrganizationRelation.organization_a_id == organization_b_id)
        & (OrganizationRelation.organization_b_id == organization_a_id),
    )


def establish_relation(
    db: Session,
    organization_a: Organization,
    organization_b: Organization,
    relation_type: OrganizationRelationType,
    *,
    reason: str = "",
) -> OrganizationRelation:
    if organization_a.id == organization_b.id:
        raise OrganizationError("Uma organização não pode ter uma relação consigo mesma.")
    existing = (
        db.query(OrganizationRelation)
        .filter(
            _pair_filter(organization_a.id, organization_b.id),
            OrganizationRelation.relation_type == relation_type,
            OrganizationRelation.status == OrganizationRelationStatus.ACTIVE,
        )
        .first()
    )
    if existing is not None:
        return existing

    world_minute = get_world_time(db, organization_a.campaign_id).total_minutes()
    relation = OrganizationRelation(
        organization_a_id=organization_a.id,
        organization_b_id=organization_b.id,
        relation_type=relation_type,
        reason=reason,
        status=OrganizationRelationStatus.ACTIVE,
        established_world_minute=world_minute,
    )
    db.add(relation)
    db.flush()

    log_event(
        db,
        organization_a.campaign_id,
        EventType.ORGANIZATION_RELATION_ESTABLISHED,
        actor_type="organization",
        actor_id=organization_a.id,
        payload={
            "organization_b_id": organization_b.id,
            "relation_type": relation_type,
            "reason": reason,
        },
        occurred_world_minute=world_minute,
    )
    return relation


def end_relation(db: Session, relation: OrganizationRelation, *, reason: str = "") -> OrganizationRelation:
    if relation.status != OrganizationRelationStatus.ACTIVE:
        return relation
    world_minute = get_world_time(db, _campaign_id(db, relation)).total_minutes()
    relation.status = OrganizationRelationStatus.ENDED
    relation.ended_world_minute = world_minute
    db.flush()

    log_event(
        db,
        _campaign_id(db, relation),
        EventType.ORGANIZATION_RELATION_ENDED,
        actor_type="organization",
        actor_id=relation.organization_a_id,
        payload={
            "organization_b_id": relation.organization_b_id,
            "relation_type": relation.relation_type,
            "reason": reason,
        },
        occurred_world_minute=world_minute,
    )
    return relation


def _campaign_id(db: Session, relation: OrganizationRelation) -> str:
    organization = db.get(Organization, relation.organization_a_id)
    return organization.campaign_id


def active_relations_between(
    db: Session, organization_a_id: str, organization_b_id: str
) -> list[OrganizationRelation]:
    return (
        db.query(OrganizationRelation)
        .filter(
            _pair_filter(organization_a_id, organization_b_id),
            OrganizationRelation.status == OrganizationRelationStatus.ACTIVE,
        )
        .order_by(OrganizationRelation.established_world_minute)
        .all()
    )


def relation_history_between(
    db: Session, organization_a_id: str, organization_b_id: str
) -> list[OrganizationRelation]:
    return (
        db.query(OrganizationRelation)
        .filter(_pair_filter(organization_a_id, organization_b_id))
        .order_by(OrganizationRelation.established_world_minute)
        .all()
    )
