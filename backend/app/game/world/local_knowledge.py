from sqlalchemy.orm import Session

from app.core.enums import KnowerType
from app.db.models.knowledge import KnowledgeFact
from app.db.models.location import Location, LocationConnection
from app.db.models.npc import NPC
from app.game.npcs.service import teach_fact


def _ensure_fact(
    db: Session,
    campaign_id: str,
    *,
    fact_key: str,
    subject: str,
    statement: str,
) -> KnowledgeFact:
    fact = (
        db.query(KnowledgeFact)
        .filter(
            KnowledgeFact.campaign_id == campaign_id,
            KnowledgeFact.fact_key == fact_key,
        )
        .first()
    )
    if fact is None:
        fact = KnowledgeFact(
            campaign_id=campaign_id,
            fact_key=fact_key,
            subject=subject,
            statement=statement,
        )
        db.add(fact)
        db.flush()
    else:
        # This is derived public Canon. Keeping it synchronized is safe when
        # an old campaign predates the facts or generated names were repaired.
        fact.subject = subject
        fact.statement = statement
    return fact


def ensure_settlement_public_knowledge(
    db: Session,
    campaign_id: str,
    location_id: str | None,
) -> None:
    """Materialize ordinary local knowledge for a settlement and its services.

    Service locations and their workers already exist mechanically, but older
    campaigns had no knowledge facts connecting them. That left an informed
    local NPC with no authorized answer and encouraged the narrator to invent
    a blacksmith, an innkeeper, and directions. Route facts use the connection
    as their subject so teaching one to the player also discovers the real
    route and destination through ``teach_fact``'s existing contract.
    """
    if location_id is None:
        return
    current = db.get(Location, location_id)
    if current is None or current.region_id is None:
        return

    settlement = current
    if current.parent_location_id is not None:
        parent = db.get(Location, current.parent_location_id)
        if parent is not None:
            settlement = parent

    services = (
        db.query(Location)
        .filter(
            Location.parent_location_id == settlement.id,
            Location.region_id == settlement.region_id,
        )
        .order_by(Location.id)
        .all()
    )
    if not services:
        return

    local_npcs = (
        db.query(NPC)
        .filter(
            NPC.campaign_id == campaign_id,
            NPC.location_id == settlement.id,
            NPC.alive.is_(True),
        )
        .all()
    )
    if not local_npcs:
        return

    for service in services:
        connection = (
            db.query(LocationConnection)
            .filter(
                LocationConnection.from_location_id == settlement.id,
                LocationConnection.to_location_id == service.id,
                LocationConnection.active.is_(True),
            )
            .first()
        )
        if connection is None:
            continue

        route_fact = _ensure_fact(
            db,
            campaign_id,
            fact_key=f"public_service_route:{connection.id}",
            subject=f"connection:{connection.id}",
            statement=(
                f"{service.name} fica a {connection.direction} da praça de "
                f"{settlement.name}."
            ),
        )
        workers = (
            db.query(NPC)
            .filter(
                NPC.campaign_id == campaign_id,
                NPC.workplace_location_id == service.id,
                NPC.alive.is_(True),
            )
            .order_by(NPC.id)
            .all()
        )
        worker_facts = [
            _ensure_fact(
                db,
                campaign_id,
                fact_key=f"public_service_worker:{worker.id}",
                subject=f"connection:{connection.id}",
                statement=(
                    f"{worker.name} trabalha como {worker.role} em {service.name}."
                ),
            )
            for worker in workers
        ]

        for npc in local_npcs:
            for fact in (route_fact, *worker_facts):
                teach_fact(
                    db,
                    campaign_id,
                    fact.fact_key,
                    KnowerType.NPC,
                    npc.id,
                    source="conhecimento público local",
                )

