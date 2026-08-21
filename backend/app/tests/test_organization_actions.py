"""Phase 13K — Organization Actions.

record_organization_action is the sole authoritative write path.
propose_organization_action mirrors Phase 11J/12H's proposal-then-
validate pattern: the LLM only picks from a small controlled vocabulary
and phrases a description grounded in real goals/needs/resources — an
invented numeric claim is rejected and the function returns None rather
than forcing a fabricated action to exist.
"""

from app.ai.llm_service import LLMService, LLMServiceError
from app.core.enums import (
    OrganizationActionType,
    OrganizationNeedCategory,
    OrganizationOrigin,
    OrganizationType,
)
from app.game.organizations.actions import (
    OrganizationActionError,
    organization_action_history,
    propose_organization_action,
    record_organization_action,
)
from app.game.organizations.goals import create_goal, create_need
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region

import pytest


class ScriptedLLM(LLMService):
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def generate(self, system: str, prompt: str) -> str:
        self.calls += 1
        return self.response


class UnavailableLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        raise LLMServiceError("Ollama indisponível.")


def _setup(db_session):
    campaign = create_campaign(db_session, "Organization Actions")
    region, village = seed_initial_region(db_session, campaign.id)
    org = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    db_session.flush()
    return campaign, org


def test_record_organization_action_requires_a_description(db_session):
    campaign, org = _setup(db_session)

    with pytest.raises(OrganizationActionError):
        record_organization_action(db_session, org, OrganizationActionType.OTHER, "  ")


def test_recorded_actions_are_all_queryable(db_session):
    campaign, org = _setup(db_session)
    record_organization_action(db_session, org, OrganizationActionType.OTHER, "Primeira ação.")
    record_organization_action(db_session, org, OrganizationActionType.OTHER, "Segunda ação.")

    history = organization_action_history(db_session, org.id)

    assert {a.description for a in history} == {"Primeira ação.", "Segunda ação."}


def test_valid_grounded_proposal_is_accepted(db_session):
    campaign, org = _setup(db_session)
    create_goal(db_session, org, "Manter a estrada do norte segura.")
    create_need(
        db_session, org, "Mais caçadores disponíveis.",
        category=OrganizationNeedCategory.SKILLED_MEMBERS,
    )
    llm = ScriptedLLM(
        '{"action_type": "PUBLISH_NOTICE", '
        '"description": "Publicar um aviso buscando caçadores para a estrada do norte."}'
    )

    action = propose_organization_action(db_session, campaign.id, llm, org)

    assert action is not None
    assert action.action_type == OrganizationActionType.PUBLISH_NOTICE
    assert llm.calls == 1


def test_proposal_with_an_invented_numeric_claim_is_rejected(db_session):
    campaign, org = _setup(db_session)
    llm = ScriptedLLM(
        '{"action_type": "PUBLISH_NOTICE", '
        '"description": "Oferecer 200 moedas de recompensa por caçadores."}'
    )

    action = propose_organization_action(db_session, campaign.id, llm, org)

    assert action is None
    assert llm.calls == 2


def test_proposal_with_an_invalid_action_type_is_rejected(db_session):
    campaign, org = _setup(db_session)
    llm = ScriptedLLM('{"action_type": "START_A_WAR", "description": "Guerra total."}')

    action = propose_organization_action(db_session, campaign.id, llm, org)

    assert action is None


def test_unavailable_llm_produces_no_action_not_an_error(db_session):
    campaign, org = _setup(db_session)

    action = propose_organization_action(db_session, campaign.id, UnavailableLLM(), org)

    assert action is None
    assert organization_action_history(db_session, org.id) == []
