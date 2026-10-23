from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.enums import (
    CombatActorType,
    NoticeStatus,
    OrganizationMembershipStatus,
)
from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.notice import Notice
from app.db.models.npc import NPC
from app.db.models.organization import OrganizationMember, OrganizationRole
from app.db.models.simulated_player import SimulatedPlayer
from app.game.groups.service import active_group_for_member, active_group_members
from app.game.organizations import guild_goals
from app.game.organizations.player_guilds import known_relations
from app.game.organizations.reputation import (
    organization_reputation_category,
    organization_reputation_score,
)
from app.game.organizations.visibility import visible_organizations_for_character
from app.schemas.social import (
    ActiveGroupResponse,
    GroupMemberResponse,
    OrganizationGoalResponse,
    OrganizationRelationResponse,
    OrganizationSummaryResponse,
    SocialStateResponse,
)

router = APIRouter(prefix="/api/campaigns", tags=["social"])


def _character_or_404(db: Session, campaign_id: str, character_id: str) -> Character:
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado nesta campanha.")
    return character


def _guild_progress(db: Session, organization, known_ids: set[str], *, member: bool) -> dict:
    """Shared goal (members only — outsiders don't know a guild's plans) and
    relations with organizations the character also knows of."""
    goal = guild_goals.current_goal(db, organization) if member else None
    return {
        "goal": (
            OrganizationGoalResponse(description=goal.description, progress=goal.progress, target=goal.target)
            if goal is not None and goal.target
            else None
        ),
        "goals_achieved": guild_goals.achieved_count(db, organization) if member else 0,
        "relations": [
            OrganizationRelationResponse(organization_name=other.name, relation_type=relation_type)
            for other, relation_type in known_relations(db, organization, known_ids)
        ],
    }


def _actor_name(db: Session, actor_type: str, actor_id: str) -> str:
    model = {
        CombatActorType.CHARACTER: Character,
        CombatActorType.NPC: NPC,
        CombatActorType.SIMULATED_PLAYER: SimulatedPlayer,
    }.get(actor_type)
    actor = db.get(model, actor_id) if model is not None else None
    return actor.name if actor is not None else "Pessoa desconhecida"


def _active_membership(db: Session, organization_id: str, character_id: str):
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.member_type == CombatActorType.CHARACTER,
            OrganizationMember.member_id == character_id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
        .first()
    )


def _leader(db: Session, organization_id: str) -> tuple[str | None, str | None]:
    row = (
        db.query(OrganizationMember, OrganizationRole)
        .join(OrganizationRole, OrganizationMember.role_id == OrganizationRole.id)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
        .order_by(OrganizationRole.rank_order, OrganizationMember.joined_world_minute)
        .first()
    )
    if row is None:
        return None, None
    member, role = row
    return _actor_name(db, member.member_type, member.member_id), role.title


@router.get("/{campaign_id}/social", response_model=SocialStateResponse)
def get_social_state(
    campaign_id: str,
    character_id: str,
    db: Session = Depends(get_db),
) -> SocialStateResponse:
    character = _character_or_404(db, campaign_id, character_id)
    organizations: list[OrganizationSummaryResponse] = []
    visible = visible_organizations_for_character(db, character)
    known_ids = {organization.id for organization in visible}
    for organization in visible:
        membership = _active_membership(db, organization.id, character.id)
        role = db.get(OrganizationRole, membership.role_id) if membership and membership.role_id else None
        leader_name, leader_title = _leader(db, organization.id)
        headquarters = (
            db.get(Location, organization.headquarters_location_id)
            if organization.headquarters_location_id
            else None
        )
        reputation_score = organization_reputation_score(
            db, organization.id, CombatActorType.CHARACTER, character.id
        )
        active_notices = (
            db.query(Notice)
            .filter(
                Notice.author_organization_id == organization.id,
                Notice.status == NoticeStatus.ACTIVE,
            )
            .count()
        )
        organizations.append(
            OrganizationSummaryResponse(
                id=organization.id,
                name=organization.name,
                organization_type=organization.organization_type,
                description=organization.description,
                status=organization.status,
                origin=organization.origin,
                formality=organization.formality,
                transported_people_stance=organization.transported_people_stance,
                headquarters_name=headquarters.name if headquarters else None,
                leader_name=leader_name,
                leader_title=leader_title,
                membership="MEMBER" if membership is not None else "NON_MEMBER",
                role=role.title if role else None,
                reputation=organization_reputation_category(reputation_score),
                active_notices=active_notices,
                focus=organization.focus,
                **_guild_progress(db, organization, known_ids, member=membership is not None),
            )
        )

    group = active_group_for_member(db, CombatActorType.CHARACTER, character.id)
    active_group = None
    if group is not None:
        members = [
            GroupMemberResponse(
                actor_type=member.member_type,
                actor_id=member.member_id,
                name=_actor_name(db, member.member_type, member.member_id),
                leader=(
                    group.leader_type == member.member_type
                    and group.leader_id == member.member_id
                ),
            )
            for member in active_group_members(db, group.id)
        ]
        active_group = ActiveGroupResponse(
            id=group.id,
            name=group.name,
            group_type=group.group_type,
            purpose=group.purpose,
            members=members,
        )

    return SocialStateResponse(organizations=organizations, active_group=active_group)
