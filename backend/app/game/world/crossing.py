"""Phase 16F — Crossing Feasibility & Hazard Evaluation.

evaluate_crossing_feasibility is a preview, never a gate. It reads
several already-real, already-independent systems — money (Phase 14),
companions (Phase 13 Group), route knowledge (the Knowledge system),
current seasonal accessibility (16E) — and combines them into an
advisory verdict. It never blocks travel and never checks
Character.level: spec explicitly rejects "if level >= 30:
allow_crossing()" — a well-prepared low-level character can outscore an
unprepared high-level one here, by design.

One honest limitation, stated rather than hidden: Everreach's Item
system (Phase 10) has no tag/category taxonomy for "cold-weather gear"
vs "waterskin" vs anything else route-relevant — ItemDefinition.type is
a free string with no such vocabulary, and building one now to make
this evaluator falsely precise would be exactly the kind of parallel
system the spec repeatedly warns against. Equipment's contribution here
is deliberately coarse (how much a character carries at all, not
whether it's the *right* gear) until Phase 10 grows that vocabulary for
its own reasons.

"DO NOT SPOIL RISK": the returned assessment never repeats a
BoundaryBarrier's or BoundaryRoute's own description text — only
generic, mechanical labels a character could plausibly reason about
themselves (spec's Logan-facing "travelers disappear in the gorge", not
"WYVERN LEVEL 37").
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, CrossingFeasibilityVerdict, KnowerType
from app.db.models.boundary_route import BoundaryRoute
from app.db.models.currency import CurrencyHolding
from app.db.models.item import ItemInstance
from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower
from app.game.groups.service import active_group_for_member, active_group_members
from app.game.world.boundaries import current_route_accessibility

BRONZE_COST_PER_DISTANCE_UNIT = 2
EQUIPMENT_READINESS_ITEM_THRESHOLD = 5


@dataclass
class CrossingFeasibilityAssessment:
    verdict: str
    accessibility: str
    estimated_cost_bronze: int
    money_bronze: int
    companion_count: int
    knows_route: bool
    concerns: list[str] = field(default_factory=list)


def _character_money_bronze(db: Session, character_id: str) -> int:
    total = (
        db.query(CurrencyHolding)
        .filter(
            CurrencyHolding.owner_type == CombatActorType.CHARACTER.value,
            CurrencyHolding.owner_id == character_id,
        )
        .all()
    )
    return sum(holding.amount_bronze for holding in total)


def _character_companion_count(db: Session, character_id: str) -> int:
    group = active_group_for_member(db, CombatActorType.CHARACTER, character_id)
    if group is None:
        return 0
    members = active_group_members(db, group.id)
    return max(0, len(members) - 1)


def _character_knows_route(db: Session, campaign_id: str, character_id: str, route: BoundaryRoute) -> bool:
    if not route.knowledge_fact_key:
        return False
    fact = (
        db.query(KnowledgeFact)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeFact.fact_key == route.knowledge_fact_key,
        )
        .first()
    )
    if fact is None:
        return False
    knower = (
        db.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id,
            KnowledgeKnower.knower_type == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id == character_id,
        )
        .first()
    )
    return knower is not None


def _character_carried_item_count(db: Session, character_id: str) -> int:
    return (
        db.query(ItemInstance)
        .filter(
            ItemInstance.location_type.in_(("CHARACTER", "CHARACTER_EQUIPPED")),
            ItemInstance.location_ref == character_id,
        )
        .count()
    )


def evaluate_crossing_feasibility(
    db: Session,
    campaign_id: str,
    character_id: str,
    route: BoundaryRoute,
) -> CrossingFeasibilityAssessment:
    accessibility = current_route_accessibility(db, campaign_id, route)
    estimated_cost = int(route.estimated_distance * BRONZE_COST_PER_DISTANCE_UNIT)
    money = _character_money_bronze(db, character_id)
    companions = _character_companion_count(db, character_id)
    knows_route = _character_knows_route(db, campaign_id, character_id, route)
    carried_items = _character_carried_item_count(db, character_id)

    score = 0
    concerns: list[str] = []

    if accessibility == "OPEN":
        score += 2
    elif accessibility == "RISKY":
        score += 0
    else:
        score -= 3
        concerns.append("A época do ano torna essa travessia extremamente arriscada.")

    if money >= estimated_cost:
        score += 1
    else:
        score -= 2
        concerns.append("Recursos insuficientes para suprimentos de uma jornada dessa duração.")

    if companions > 0:
        score += 1
    else:
        concerns.append("Nenhum companheiro para dividir os riscos da travessia.")

    if knows_route:
        score += 1
    else:
        score -= 1
        concerns.append("Pouco se sabe sobre os perigos reais dessa rota.")

    if carried_items >= EQUIPMENT_READINESS_ITEM_THRESHOLD:
        score += 1
    else:
        concerns.append("Equipamento carregado parece insuficiente para uma expedição longa.")

    if score >= 3:
        verdict = CrossingFeasibilityVerdict.FEASIBLE.value
    elif score >= 0:
        verdict = CrossingFeasibilityVerdict.POSSIBLE_BUT_DANGEROUS.value
    else:
        verdict = CrossingFeasibilityVerdict.LIKELY_TO_FAIL.value

    return CrossingFeasibilityAssessment(
        verdict=verdict,
        accessibility=accessibility,
        estimated_cost_bronze=estimated_cost,
        money_bronze=money,
        companion_count=companions,
        knows_route=knows_route,
        concerns=concerns,
    )
