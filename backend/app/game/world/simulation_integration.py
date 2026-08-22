"""Phase 16T — Simulation Integration.

Audited every simulation entry point that could plausibly assume "only
one Region exists" (world_simulation, npc_simulation, player_simulation,
organization actions, economic world events, quest emergence) — per the
16A audit, none of them hardcode a region id or otherwise special-case
region:0; they all operate on whatever Location/region_id a character,
NPC, or event already carries. The one real gap: nothing ever made a
newly materialized Region's own settlements eligible destinations for
the Phase 7 "Primeira Chegada continues" arrival system
(app.game.players.service) — that wiring only ever happened inside
seed_initial_region, for the starting Region alone. Without this, a
neighboring Region would sit fully generated but never actually receive
new arrivals, contradicting the spec's own "the new Region becomes part
of the living world immediately after persistence... Simulation may act
there even if Logan knows nothing about it."

enable_simulated_player_arrivals_for_region closes that gap, reusing
the exact same primitive (set_simulated_player_arrival_location_enabled)
and the exact same population_tier-weighted selection
(select_simulated_player_arrival_location) the starting Region already
relies on — no parallel arrival mechanism for neighboring Regions.
"""

from sqlalchemy.orm import Session

from app.db.models.location import Location
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion
from app.game.players.service import set_simulated_player_arrival_location_enabled


def enable_simulated_player_arrivals_for_region(db: Session, campaign_id: str, region_id: str) -> list[str]:
    """Marks every settlement Location in region_id as an eligible
    automatic-arrival destination. Returns the enabled location ids."""
    settlement_location_ids = [
        row[0]
        for row in db.query(Settlement.location_id)
        .join(Location, Location.id == Settlement.location_id)
        .join(Subregion, Subregion.id == Location.subregion_id)
        .filter(Subregion.region_id == region_id)
        .all()
    ]
    for location_id in settlement_location_ids:
        set_simulated_player_arrival_location_enabled(db, campaign_id, location_id, enabled=True)
    return settlement_location_ids
