"""Phase 13I — Organization Goals & Needs.

Goal != Need: a goal is the qualitative "why" (free text); a need is a
concrete, categorized gap, optionally serving a specific goal. priority
is a persisted hook, not an autonomous strategy AI.
"""

import pytest

from app.core.enums import (
    OrganizationGoalStatus,
    OrganizationNeedCategory,
    OrganizationNeedStatus,
    OrganizationOrigin,
    OrganizationType,
)
from app.game.organizations.goals import (
    active_goals,
    create_goal,
    create_need,
    open_needs,
    set_goal_status,
    set_need_status,
)
from app.game.organizations.service import OrganizationError, create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Organization Goals")
    region, village = seed_initial_region(db_session, campaign.id)
    org = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    db_session.flush()
    return campaign, org


def test_goal_and_need_are_independent_concepts(db_session):
    campaign, org = _setup(db_session)

    goal = create_goal(db_session, org, "Manter a estrada do norte segura.")
    need = create_need(
        db_session, org, "Mais caçadores disponíveis.",
        category=OrganizationNeedCategory.SKILLED_MEMBERS, goal_id=goal.id,
    )

    assert need.goal_id == goal.id
    assert need.description != goal.description


def test_a_need_may_exist_without_a_goal(db_session):
    campaign, org = _setup(db_session)

    need = create_need(
        db_session, org, "Flechas.", category=OrganizationNeedCategory.WEAPONS,
    )

    assert need.goal_id is None


def test_need_must_reference_a_goal_of_the_same_organization(db_session):
    campaign, org = _setup(db_session)
    other_org = create_organization(
        db_session, campaign.id, "Templo de Cardal",
        organization_type=OrganizationType.RELIGIOUS, origin=OrganizationOrigin.NATIVE,
    )
    foreign_goal = create_goal(db_session, other_org, "Converter mais fiéis.")

    with pytest.raises(OrganizationError):
        create_need(
            db_session, org, "Incenso.", category=OrganizationNeedCategory.MATERIALS,
            goal_id=foreign_goal.id,
        )


def test_active_goals_orders_by_priority(db_session):
    campaign, org = _setup(db_session)
    create_goal(db_session, org, "Objetivo secundário.", priority=1)
    urgent = create_goal(db_session, org, "Objetivo urgente.", priority=10)

    goals = active_goals(db_session, org.id)

    assert goals[0].id == urgent.id


def test_achieved_goal_is_excluded_from_active_goals(db_session):
    campaign, org = _setup(db_session)
    goal = create_goal(db_session, org, "Objetivo concluído.")
    set_goal_status(db_session, goal, OrganizationGoalStatus.ACHIEVED)

    assert active_goals(db_session, org.id) == []


def test_fulfilled_need_is_excluded_from_open_needs(db_session):
    campaign, org = _setup(db_session)
    need = create_need(db_session, org, "Flechas.", category=OrganizationNeedCategory.WEAPONS)
    set_need_status(db_session, need, OrganizationNeedStatus.FULFILLED)

    assert open_needs(db_session, org.id) == []


def test_goal_requires_a_description(db_session):
    campaign, org = _setup(db_session)

    with pytest.raises(OrganizationError):
        create_goal(db_session, org, "   ")
