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
    focus: str | None = None
    goal: "OrganizationGoalResponse | None" = None
    goals_achieved: int = 0
    relations: list["OrganizationRelationResponse"] = []


class OrganizationGoalResponse(BaseModel):
    description: str
    progress: int
    target: int


class OrganizationRelationResponse(BaseModel):
    organization_name: str
    relation_type: str


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


OrganizationSummaryResponse.model_rebuild()
