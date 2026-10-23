"""Player-safe read helpers for Phase 13 organizations.

An organization existing in the database is not enough to expose it.  This
module is the shared visibility boundary used by both the narrator context
and the HTTP projection shown to the player.
"""

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    OrganizationMembershipStatus,
    OrganizationVisibility,
)
from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.organization import Organization, OrganizationMember
from app.db.models.quest import CharacterQuest, Quest
from app.game.quests.discovery import is_quest_known_to_character


def _current_location_lineage(db: Session, location_id: str | None) -> set[str]:
    """Return the current place and its physical parents.

    A village council headquartered in the village remains locally visible
    while the character is inside one of that village's buildings.  Sibling
    headquarters (for example another guild elsewhere in the village) are
    intentionally not included.
    """
    lineage: set[str] = set()
    current_id = location_id
    while current_id and current_id not in lineage:
        lineage.add(current_id)
        location = db.get(Location, current_id)
        current_id = location.parent_location_id if location is not None else None
    return lineage


def visible_organizations_for_character(
    db: Session,
    character: Character,
) -> list[Organization]:
    """Organizations the character can legitimately identify right now.

    Visibility comes from one of three authoritative facts: active
    membership, a public headquarters at the current physical place (or one
    of its parents), or a quest the character actually participates in that
    names the sponsoring organization.  This never exposes private/secret
    organizations merely because a row exists.
    """
    organization_ids = {
        row.organization_id
        for row in db.query(OrganizationMember).filter(
            OrganizationMember.member_type == CombatActorType.CHARACTER,
            OrganizationMember.member_id == character.id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
    }

    location_ids = _current_location_lineage(db, character.location_id)
    if location_ids:
        organization_ids.update(
            organization.id
            for organization in db.query(Organization).filter(
                Organization.campaign_id == character.campaign_id,
                Organization.visibility == OrganizationVisibility.PUBLIC,
                Organization.headquarters_location_id.in_(location_ids),
            )
        )

    participating_quest_ids = {
        quest_id
        for (quest_id,) in db.query(CharacterQuest.quest_id).filter(
            CharacterQuest.character_id == character.id
        )
    }
    sponsored_quests = (
        db.query(Quest)
        .join(Organization, Organization.id == Quest.sponsoring_organization_id)
        .filter(
            Quest.region_id == character.region_id,
            Organization.campaign_id == character.campaign_id,
            Organization.visibility == OrganizationVisibility.PUBLIC,
        )
        .all()
    )
    organization_ids.update(
        quest.sponsoring_organization_id
        for quest in sponsored_quests
        if quest.sponsoring_organization_id is not None
        and (
            quest.id in participating_quest_ids
            or is_quest_known_to_character(
                db, character.campaign_id, character.id, quest.id
            )
        )
    )

    # A transported guild has no public seat: the character knows of it by
    # having learned it exists (from a member, or an NPC naming it).
    from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
    from app.core.enums import KnowerType

    organization_ids.update(
        fact_key.split(":")[1]
        for (fact_key,) in db.query(KnowledgeFact.fact_key)
        .join(KnowledgeKnower, KnowledgeKnower.fact_id == KnowledgeFact.id)
        .filter(
            KnowledgeFact.campaign_id == character.campaign_id,
            KnowledgeFact.fact_key.like("organization:%:exists"),
            KnowledgeKnower.knower_type == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id == character.id,
        )
    )

    if not organization_ids:
        return []
    return (
        db.query(Organization)
        .filter(
            Organization.campaign_id == character.campaign_id,
            Organization.id.in_(organization_ids),
        )
        .order_by(Organization.name)
        .all()
    )
