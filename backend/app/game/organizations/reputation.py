"""Phase 13G — Reputation.

NOT personal relationship (app.game.relationships.service stays the
system for "Osgar personally likes Logan") — this is what an
Organization, as an entity, thinks of a character/NPC. Never a bare
score = -72 as the only source of truth: every change is an append-only,
explained record (mirroring DomainEvidenceRecord's shape), and the
category a caller actually reads is derived from those records.

REPUTATION IS KNOWLEDGE-DEPENDENT: an organization does not magically
know what happened. award_organization_reputation's witness_fact_key
reuses the existing Knowledge system (Phase 4/5) — when given, the
change is refused unless at least one of the organization's own NPC
members already knows that fact. Callers awarding reputation for
something the organization was itself a direct party to (e.g. completing
a contract for it) can omit witness_fact_key — direct involvement is its
own witness. Public/social reputation beyond one organization's opinion
(the spec's "the transported man who helped during the fire") is left
architecturally compatible but not built — no omniscient fame meter.
"""

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    EventType,
    KnowerType,
    OrganizationReputationCategory,
)
from app.db.models.organization import Organization
from app.db.models.organization_reputation import OrganizationReputationRecord
from app.game.npcs.service import knows
from app.game.organizations.roles import active_members
from app.game.organizations.service import OrganizationError
from app.game.time.clock import get_world_time
from app.services.event_log import log_event

_CATEGORY_THRESHOLDS: tuple[tuple[OrganizationReputationCategory, int], ...] = (
    (OrganizationReputationCategory.TRUSTED, 20),
    (OrganizationReputationCategory.RELIABLE, 5),
    (OrganizationReputationCategory.NEUTRAL, -5),
    (OrganizationReputationCategory.DISTRUSTED, -20),
)


def award_organization_reputation(
    db: Session,
    organization: Organization,
    subject_type: CombatActorType,
    subject_id: str,
    *,
    delta: int,
    reason: str,
    witness_fact_key: str | None = None,
) -> OrganizationReputationRecord:
    if not reason.strip():
        raise OrganizationError("Uma mudança de reputação precisa de um motivo explicável.")
    if witness_fact_key is not None:
        witnessed = any(
            member.member_type == CombatActorType.NPC
            and knows(db, KnowerType.NPC, member.member_id, witness_fact_key, organization.campaign_id)
            for member in active_members(db, organization.id)
        )
        if not witnessed:
            raise OrganizationError(
                "Nenhum membro da organização tem conhecimento do fato citado — "
                "a reputação não muda sem testemunha."
            )

    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    record = OrganizationReputationRecord(
        organization_id=organization.id,
        subject_type=subject_type,
        subject_id=subject_id,
        delta=delta,
        reason=reason,
        world_minute=world_minute,
    )
    db.add(record)
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_REPUTATION_CHANGED,
        actor_type=subject_type.lower(),
        actor_id=subject_id,
        payload={"organization_id": organization.id, "delta": delta, "reason": reason},
        occurred_world_minute=world_minute,
    )
    return record


def organization_reputation_history(
    db: Session, organization_id: str, subject_type: CombatActorType, subject_id: str
) -> list[OrganizationReputationRecord]:
    return (
        db.query(OrganizationReputationRecord)
        .filter(
            OrganizationReputationRecord.organization_id == organization_id,
            OrganizationReputationRecord.subject_type == subject_type,
            OrganizationReputationRecord.subject_id == subject_id,
        )
        .order_by(OrganizationReputationRecord.world_minute)
        .all()
    )


def organization_reputation_score(
    db: Session, organization_id: str, subject_type: CombatActorType, subject_id: str
) -> int:
    return sum(
        record.delta
        for record in organization_reputation_history(db, organization_id, subject_type, subject_id)
    )


def organization_reputation_category(score: int) -> OrganizationReputationCategory:
    for category, threshold in _CATEGORY_THRESHOLDS:
        if score >= threshold:
            return category
    return OrganizationReputationCategory.HOSTILE
