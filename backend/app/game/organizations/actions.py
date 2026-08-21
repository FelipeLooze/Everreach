"""Phase 13K — Organization Actions.

ORGANIZATION ACTION AUTHORITY: the Narrator never decides an
organization acted — only an authoritative OrganizationAction row does.
record_organization_action is the sole write path (the "clean hook"
instead of a hardcoded per-action chain); propose_organization_action is
the LLM-assisted flow, mirroring Phase 11J/12H's proposal-then-validate
pattern exactly: the LLM only ever picks from a small controlled
vocabulary and phrases a description grounded in the organization's real
goals/needs/resources — it never decides an action happened on its own.

Most of the spec's 17 example actions (patrol, negotiate, send an
expedition...) have no backend mechanism yet — those, when proposed,
persist as OTHER: a validated, recorded intent, not a mechanized effect.
Only RECRUIT_MEMBER/EXPEL_MEMBER/PROMOTE_MEMBER reuse a real Phase 13F
mechanism today.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.llm_service import LLMService, LLMServiceError
from app.core.enums import CombatActorType, EventType, OrganizationActionType
from app.core.logging import get_logger
from app.db.models.organization import Organization, OrganizationAction
from app.game.organizations.goals import active_goals, open_needs
from app.game.time.clock import get_world_time
from app.services.event_log import log_event

logger = get_logger("game")

_PROMPT_PATH = Path(__file__).parents[2] / "ai" / "prompts" / "organization_action_proposal_system.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_MAX_ATTEMPTS = 2

_NUMERIC_CLAIM_PATTERN = re.compile(
    r"\b\d+([.,]\d+)?\s*(de\s+)?(moedas?|ouro|prata|pessoas?|dias?|semanas?)\b",
    re.IGNORECASE,
)


class OrganizationActionError(Exception):
    pass


@dataclass(frozen=True)
class OrganizationActionProposal:
    action_type: OrganizationActionType
    description: str


def record_organization_action(
    db: Session,
    organization: Organization,
    action_type: OrganizationActionType,
    description: str,
    *,
    actor_type: CombatActorType | None = None,
    actor_id: str | None = None,
) -> OrganizationAction:
    if not description.strip():
        raise OrganizationActionError("Uma ação organizacional precisa de uma descrição.")
    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    action = OrganizationAction(
        organization_id=organization.id,
        action_type=action_type,
        description=description,
        actor_type=actor_type,
        actor_id=actor_id,
        world_minute=world_minute,
    )
    db.add(action)
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_ACTION_RESOLVED,
        actor_type=(actor_type.lower() if actor_type else "organization"),
        actor_id=actor_id or organization.id,
        payload={"organization_id": organization.id, "action_type": action_type},
        occurred_world_minute=world_minute,
    )
    return action


def organization_action_history(db: Session, organization_id: str) -> list[OrganizationAction]:
    return (
        db.query(OrganizationAction)
        .filter(OrganizationAction.organization_id == organization_id)
        .order_by(OrganizationAction.world_minute.desc())
        .all()
    )


def _proposal_summary_text(db: Session, organization: Organization) -> str:
    goals = active_goals(db, organization.id)
    needs = open_needs(db, organization.id)
    lines = [f"Organização: {organization.name}"]
    lines.append(
        "Objetivos ativos: " + ("; ".join(g.description for g in goals) if goals else "nenhum")
    )
    lines.append(
        "Necessidades em aberto: "
        + ("; ".join(f"{n.description} ({n.category})" for n in needs) if needs else "nenhuma")
    )
    lines.append(f"Tesouro: {organization.treasury:g}")
    return "\n".join(lines)


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _request_action_proposal(
    llm_service: LLMService, summary_text: str, *, previous_violations: list[str] | None = None
) -> OrganizationActionProposal | None:
    prompt = f"Resumo autoritativo:\n{summary_text}"
    if previous_violations:
        prompt += (
            "\n\nSua proposta anterior violou estas regras — proponha de novo, "
            "corrigindo apenas isso:\n- " + "\n- ".join(previous_violations)
        )
    try:
        raw = llm_service.generate(_SYSTEM_PROMPT, prompt)
    except LLMServiceError:
        logger.info("organization action proposal: LLM unavailable")
        return None
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning("organization action proposal: could not parse LLM response: %r", raw)
        return None
    action_type_raw = data.get("action_type")
    description = data.get("description")
    if not isinstance(action_type_raw, str) or not isinstance(description, str) or not description.strip():
        return None
    try:
        action_type = OrganizationActionType(action_type_raw)
    except ValueError:
        return None
    return OrganizationActionProposal(action_type=action_type, description=description.strip())


def _validate_action_proposal(proposal: OrganizationActionProposal) -> list[str]:
    violations: list[str] = []
    if _NUMERIC_CLAIM_PATTERN.search(proposal.description):
        violations.append(
            "a proposta inclui um valor numérico (moeda, pessoas, prazo) não fornecido no resumo"
        )
    return violations


def propose_organization_action(
    db: Session, campaign_id: str, llm_service: LLMService, organization: Organization
) -> OrganizationAction | None:
    """Returns None (never raises) when no valid proposal could be
    produced after retrying — an organization not deciding anything
    right now is a legitimate outcome, unlike Phase 12H's emergent quests
    where a real WorldEvent always already justified something existing."""
    summary_text = _proposal_summary_text(db, organization)

    violations: list[str] | None = None
    for _attempt in range(_MAX_ATTEMPTS):
        proposal = _request_action_proposal(llm_service, summary_text, previous_violations=violations)
        if proposal is None:
            continue
        violations = _validate_action_proposal(proposal)
        if not violations:
            return record_organization_action(
                db, organization, proposal.action_type, proposal.description
            )
        logger.warning(
            "organization action proposal for %s rejected: %s", organization.id, violations
        )

    logger.warning(
        "organization action proposal: no valid proposal for %s after %s attempts",
        organization.id,
        _MAX_ATTEMPTS,
    )
    return None
