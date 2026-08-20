from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.enums import CharacterStatus
from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.region import Region
from app.db.models.relationship import CharacterNPCRelationship
from app.db.models.simulated_player import (
    SimulatedPlayer,
    SimulatedPlayerPopulation,
)


class SimulationTier(StrEnum):
    """Amount of mechanical detail assigned during one world tick."""

    DETAILED = "DETAILED"
    RELEVANT = "RELEVANT"
    ABSTRACT = "ABSTRACT"


@dataclass(frozen=True)
class SimulationScope:
    """Immutable relevance snapshot shared by all tick subsystems.

    A campaign without an active protagonist is treated as unrestricted. This
    keeps administrative simulations and isolated domain tests deterministic.
    In a running game, physical proximity and persistent relationships define
    which entities deserve more detail.
    """

    campaign_id: str
    detailed_location_ids: frozenset[str]
    relevant_npc_ids: frozenset[str]
    unrestricted: bool
    materialized_simulated_players: int
    abstract_simulated_players: int

    def npc_tier(self, npc_id: str, location_id: str) -> SimulationTier:
        if self.unrestricted or location_id in self.detailed_location_ids:
            return SimulationTier.DETAILED
        if npc_id in self.relevant_npc_ids:
            return SimulationTier.RELEVANT
        return SimulationTier.ABSTRACT

    def simulated_player_tier(self, location_id: str) -> SimulationTier:
        if self.unrestricted or location_id in self.detailed_location_ids:
            return SimulationTier.DETAILED

        # A persistent identity is already relevant. Unmaterialized transported
        # people remain represented by aggregate population rows.
        return SimulationTier.RELEVANT


def build_simulation_scope(db: Session, campaign_id: str) -> SimulationScope:
    detailed_location_ids = frozenset(
        location_id
        for (location_id,) in (
            db.query(Character.location_id)
            .filter(
                Character.campaign_id == campaign_id,
                Character.status == CharacterStatus.ALIVE.value,
                Character.location_id.is_not(None),
            )
            .distinct()
            .all()
        )
        if location_id is not None
    )

    relevant_npc_ids = frozenset(
        npc_id
        for (npc_id,) in (
            db.query(CharacterNPCRelationship.npc_id)
            .filter(CharacterNPCRelationship.campaign_id == campaign_id)
            .distinct()
            .all()
        )
    )

    materialized_count = (
        db.query(func.count(SimulatedPlayer.id))
        .filter(SimulatedPlayer.campaign_id == campaign_id)
        .scalar()
        or 0
    )

    abstract_count = (
        db.query(
            func.coalesce(
                func.sum(SimulatedPlayerPopulation.abstract_count),
                0,
            )
        )
        .join(
            Location,
            SimulatedPlayerPopulation.location_id == Location.id,
        )
        .join(Region, Location.region_id == Region.id)
        .filter(Region.campaign_id == campaign_id)
        .scalar()
        or 0
    )

    return SimulationScope(
        campaign_id=campaign_id,
        detailed_location_ids=detailed_location_ids,
        relevant_npc_ids=relevant_npc_ids,
        unrestricted=not detailed_location_ids,
        materialized_simulated_players=int(materialized_count),
        abstract_simulated_players=int(abstract_count),
    )
