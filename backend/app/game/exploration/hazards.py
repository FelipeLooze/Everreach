"""Phase 17K — Natural Exploration Hazards.

Getting lost is the one hazard implemented here, chosen because it is
the hazard the spec's own text most directly ties to real knowledge
("Getting lost should emerge from: poor navigation, unfamiliar terrain,
bad weather, low visibility, missing landmarks, incorrect maps, route
deviation") — exactly the aspects 17A/17E already model. Not a
context-free chance: assess_navigation_risk derives HIGH/MODERATE/LOW
from whether the character actually knows the ROUTE (17E) and how
PRECISE their DIRECTION knowledge is (17B), and resolve_navigation
rolls against a DC that risk level sets — someone who has never heard
of a place is genuinely more likely to get lost trying to reach it than
someone who has walked the route before.

Deliberately NOT built here: dehydration/starvation/hypothermia/storms/
avalanches/floods and every other hazard the spec lists as *possible*.
Everreach has no hunger/thirst/temperature resource system for those to
plug into yet (confirmed: no such model exists in Phase 8/10 today) —
inventing one as a side effect of this subphase would be exactly the
kind of parallel system the spec warns against. Getting lost needed
only the time-cost primitive (app.game.time.clock.advance_world_time)
already used everywhere else in exploration (17D).
"""

import random

from sqlalchemy.orm import Session

from app.core.enums import EventType, GeographicKnowledgeAspect, GeographicPrecision, KnowerType, NavigationRisk
from app.game.dice import d20
from app.game.knowledge.geography import geographic_knowledge_precision, knows_geographic_aspect
from app.game.time.clock import advance_world_time
from app.services.event_log import log_event

_DC_BY_RISK = {
    NavigationRisk.LOW: 6,
    NavigationRisk.MODERATE: 12,
    NavigationRisk.HIGH: 17,
}
_LOST_EXTRA_MINUTES = 60


def assess_navigation_risk(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    subject_kind: str,
    entity_id: str,
) -> NavigationRisk:
    knows_route = knows_geographic_aspect(
        db, campaign_id, knower_type, knower_id, subject_kind, entity_id, GeographicKnowledgeAspect.ROUTE
    )
    direction_precision = geographic_knowledge_precision(
        db, campaign_id, knower_type, knower_id, subject_kind, entity_id, GeographicKnowledgeAspect.DIRECTION
    )

    if knows_route and direction_precision in (GeographicPrecision.GOOD, GeographicPrecision.PRECISE):
        return NavigationRisk.LOW
    if knows_route or direction_precision is not None:
        return NavigationRisk.MODERATE
    return NavigationRisk.HIGH


def resolve_navigation(
    db: Session,
    campaign_id: str,
    character_id: str,
    subject_kind: str,
    entity_id: str,
    *,
    rng: random.Random | None = None,
) -> tuple[NavigationRisk, bool, int]:
    """Returns (risk, got_lost, extra_minutes_spent)."""
    risk = assess_navigation_risk(db, campaign_id, KnowerType.PLAYER, character_id, subject_kind, entity_id)
    roll = d20(rng=rng)
    got_lost = roll.total < _DC_BY_RISK[risk]

    extra_minutes = _LOST_EXTRA_MINUTES if got_lost else 0
    if extra_minutes:
        advance_world_time(db, campaign_id, extra_minutes)
        log_event(
            db, campaign_id, EventType.NAVIGATION_HAZARD_ENCOUNTERED,
            actor_type="character", actor_id=character_id,
            payload={"risk": risk.value, "roll": roll.total, "extra_minutes": extra_minutes},
        )

    return risk, got_lost, extra_minutes
