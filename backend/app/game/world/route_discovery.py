"""Phase 16G — Alternative / Hidden Route Discovery.

Route existence is world truth the moment a route is generated (16D);
who actually knows it is decided here, reusing the existing Knowledge
system wholesale — no parallel "route discovery" table.

Deliberately NOT implemented yet (spec: "Do not prematurely implement
the complete cartography system in Phase 16" — that is Phase 17's
job): partial/inaccurate map detail, old-map fragments, and any
player-facing "search for a route" action. What exists here is the
real primitive (grant_route_knowledge) plus the one call site that
already has a natural, honest reason to know: the anchor settlement's
own local leader, wired directly into boundary creation.
"""

from sqlalchemy.orm import Session

from app.core.enums import KnowerType
from app.db.models.boundary_route import BoundaryRoute
from app.db.models.organization import Organization
from app.game.npcs.service import teach_fact


def grant_route_knowledge(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    route: BoundaryRoute,
    *,
    source: str = "exploração",
) -> None:
    if not route.knowledge_fact_key:
        return
    teach_fact(db, campaign_id, route.knowledge_fact_key, knower_type, knower_id, source=source)


def discover_route_by_exploration(db: Session, campaign_id: str, character_id: str, route: BoundaryRoute) -> bool:
    """Reaching the boundary and asking around/observing is enough to
    learn about a publicly known route — never a hidden one; those need
    a stronger, deliberate signal (an old map, a guide, ruins) that
    Phase 17 will provide the actual discovery flows for. Returns
    whether anything was actually granted."""
    if not route.is_publicly_known:
        return False
    grant_route_knowledge(db, campaign_id, KnowerType.PLAYER, character_id, route, source="exploração")
    return True


def grant_local_leader_knowledge_of_boundary(
    db: Session, campaign_id: str, anchor_location_id: str, routes: list[BoundaryRoute]
) -> None:
    """Whoever leads the settlement nearest a boundary plausibly already
    knows about its publicly known routes — the same "local knowledge"
    Phase 15J already grants its own settlement's founder/leader NPC for
    every other canonical fact about their home. Hidden routes are never
    granted this way."""
    organization = (
        db.query(Organization)
        .filter(Organization.headquarters_location_id == anchor_location_id)
        .first()
    )
    if organization is None or organization.founder_id is None:
        return

    for route in routes:
        if route.is_publicly_known:
            grant_route_knowledge(
                db, campaign_id, KnowerType.NPC, organization.founder_id, route, source="conhecimento local"
            )
