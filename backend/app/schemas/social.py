from pydantic import BaseModel


class OrganizationSummaryResponse(BaseModel):
    id: str
    name: str
    organization_type: str
    description: str
    status: str
    origin: str
    formality: str
    transported_people_stance: str | None
    headquarters_name: str | None
    leader_name: str | None
    leader_title: str | None
    membership: str
    role: str | None
    reputation: str
    active_notices: int


class GroupMemberResponse(BaseModel):
    actor_type: str
    actor_id: str
    name: str
    leader: bool


class ActiveGroupResponse(BaseModel):
    id: str
    name: str | None
    group_type: str
    purpose: str
    members: list[GroupMemberResponse]


class SocialStateResponse(BaseModel):
    organizations: list[OrganizationSummaryResponse]
    active_group: ActiveGroupResponse | None
