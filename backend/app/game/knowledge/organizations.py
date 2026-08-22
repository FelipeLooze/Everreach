"""Phase 17O — Organization & NPC Geographic Knowledge.

Organizations become real geographic knowers here — KnowerType.ORGANIZATION,
using the exact same KnowledgeFact/KnowledgeKnower machinery every other
knower already uses (grant_geographic_knowledge, known_geographic_aspects,
list_known_perspectives all already work for an Organization's own id
with zero changes). No parallel "organization intelligence" table.

"Do not automatically expose organization knowledge to every member"
(spec) is the one real rule this module enforces in code:
consult_organization_geographic_knowledge only ever transfers the
organization's own knowledge to a member who is verified to actually,
currently, actively belong (app.game.organizations.roles, Phase 13) —
reusing app.game.knowledge.sharing.propagate_geographic_knowledge (17M)
for the transfer itself (with the same "no omniscient transfer, source
must actually know it" guarantee, and the same precision-degradation
option) rather than a bespoke org-specific copy mechanism. A former
member, or anyone who was never a member, gets nothing.

"NPC knowledge should reflect their lives... Do not give generic NPCs
complete Region knowledge" was already true by construction before this
subphase — nothing anywhere in this codebase bulk-grants an NPC
knowledge of anything; every grant seen so far (Phase 15J's settlement
founders, 16G's local leaders, 17I's expedition members) is scoped to
one specific fact for one specific reason. This module doesn't need to
defend against a bulk-grant pattern that was never built.
"""

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, GeographicKnowledgeAspect, GeographicPrecision, KnowerType, KnowledgeCertainty, OrganizationMembershipStatus
from app.db.models.organization import OrganizationMember
from app.game.knowledge.geography import grant_geographic_knowledge
from app.game.knowledge.sharing import propagate_geographic_knowledge

_KNOWER_TYPE_BY_MEMBER_TYPE = {
    CombatActorType.CHARACTER.value: KnowerType.PLAYER,
    CombatActorType.NPC.value: KnowerType.NPC,
    CombatActorType.SIMULATED_PLAYER.value: KnowerType.SIMULATED_PLAYER,
}


def is_active_member(db: Session, organization_id: str, member_type: CombatActorType, member_id: str) -> bool:
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.member_type == member_type,
            OrganizationMember.member_id == member_id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
        .first()
        is not None
    )


def grant_organization_geographic_knowledge(
    db: Session,
    campaign_id: str,
    organization_id: str,
    subject_kind: str,
    entity_id: str,
    aspect: GeographicKnowledgeAspect,
    *,
    source: str = "system",
    certainty: KnowledgeCertainty = KnowledgeCertainty.CONFIRMED,
    precision: GeographicPrecision = GeographicPrecision.APPROXIMATE,
) -> None:
    grant_geographic_knowledge(
        db, campaign_id, KnowerType.ORGANIZATION, organization_id,
        subject_kind, entity_id, aspect,
        source=source, certainty=certainty, precision=precision,
    )


def consult_organization_geographic_knowledge(
    db: Session,
    campaign_id: str,
    organization_id: str,
    member_type: CombatActorType,
    member_id: str,
    subject_kind: str,
    entity_id: str,
    aspect: GeographicKnowledgeAspect,
    *,
    degrade_precision: bool = False,
) -> bool:
    """False if the member isn't actually (currently, actively) part of
    the organization — never an automatic transfer. degrade_precision
    defaults to False: consulting an organization's own written records
    (a guild's survey ledger, a guard captain's maps) is closer to
    reading a map than hearing something secondhand (17M), though a
    caller modeling a purely verbal briefing may still opt in."""
    if not is_active_member(db, organization_id, member_type, member_id):
        return False

    to_type = _KNOWER_TYPE_BY_MEMBER_TYPE.get(member_type)
    if to_type is None:
        return False

    return propagate_geographic_knowledge(
        db, campaign_id, subject_kind, entity_id, aspect,
        KnowerType.ORGANIZATION, organization_id,
        to_type, member_id,
        degrade_precision=degrade_precision,
    )
