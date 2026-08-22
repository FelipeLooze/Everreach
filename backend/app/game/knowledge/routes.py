"""Phase 17E — Route Knowledge.

Knowing two places exist does not mean knowing how to travel between
them (spec) — EXISTENCE and ROUTE are deliberately separate
GeographicKnowledgeAspect values (17A). This module is the one place
that grants BOTH halves of "a character now knows this route" at once:
- the MECHANICAL half — app.game.discovery.service.discover_connection,
  the exact same CharacterConnectionDiscovery row
  app.game.travel.service.move_character already requires to travel —
  only ever recorded for a real PLAYER Character (CharacterConnectionDiscovery
  is FK'd to characters.id specifically; NPCs/SimulatedPlayers don't
  travel through this gate at all, so their route knowledge is purely
  informational).
- the INFORMATIONAL half — a ROUTE-aspect KnowledgeFact (17A) on the
  destination, so route knowledge shows up in known_geographic_aspects/
  narrator context the same way any other geographic fact does, giving
  LocationConnection-based routes the same informational richness
  Phase 16D/16G already gave BoundaryRoute-based ones (the two were
  never merged — a LocationConnection and a BoundaryRoute are
  genuinely different-scale concepts — but both are equally "real
  knowledge" now).

KNOWN ROUTE != SAFE ROUTE (spec): this module never reads or freezes
the connection's live danger/active state into anything that gates
travel. The granted fact's statement is a snapshot of duration/danger
AT GRANT TIME (already how every fact works — statements never
self-update). app.game.travel.service.move_character still always
re-reads the connection's CURRENT danger/active before resolving a
trip: a route a character "knows" can become more dangerous, or close
entirely, without their knowledge record changing at all — nothing new
needed here, that separation already existed; this module only adds a
test proving it.
"""

from sqlalchemy.orm import Session

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType, KnowledgeCertainty
from app.db.models.location import Location, LocationConnection
from app.game.discovery.service import discover_connection
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge

_DANGER_DESCRIPTION = {
    0: "sem perigo conhecido",
    1: "pouco perigosa",
    2: "pouco perigosa",
    3: "moderadamente perigosa",
    4: "moderadamente perigosa",
    5: "moderadamente perigosa",
}


def _danger_description(danger: int) -> str:
    if danger in _DANGER_DESCRIPTION:
        return _DANGER_DESCRIPTION[danger]
    return "muito perigosa"


def route_knowledge_statement(connection: LocationConnection, destination_name: str) -> str:
    return (
        f"Uma rota leva a {destination_name}, com distância aproximada de "
        f"{connection.distance:.1f} e considerada {_danger_description(connection.danger)}."
    )


def grant_route_knowledge(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    connection: LocationConnection,
    *,
    source: str = "system",
    certainty: KnowledgeCertainty = KnowledgeCertainty.CONFIRMED,
    precision: GeographicPrecision = GeographicPrecision.APPROXIMATE,
) -> None:
    destination = db.get(Location, connection.to_location_id)

    ensure_geographic_fact(
        db, campaign_id, "location", destination.id, GeographicKnowledgeAspect.ROUTE,
        route_knowledge_statement(connection, destination.name),
    )
    grant_geographic_knowledge(
        db, campaign_id, knower_type, knower_id,
        "location", destination.id, GeographicKnowledgeAspect.ROUTE,
        source=source, certainty=certainty, precision=precision,
    )

    if knower_type == KnowerType.PLAYER:
        discover_connection(db, knower_id, connection.id)
