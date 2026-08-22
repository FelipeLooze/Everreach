"""Phase 15P — Content-on-Demand.

"The protagonist is NOT the only trigger" (spec). A simulated player
arriving somewhere Logan has never been must deep-materialize that place
too — reusing the exact same primitive real travel already uses
(app.game.world.materialization.ensure_location_materialized), not a
second parallel mechanism.
"""

from app.db.models.location import Location
from app.simulation import player_simulation
from app.game.world.seed import create_campaign, seed_initial_region


def _a_minor_settlement(db_session):
    return db_session.query(Location).filter(Location.materialization_tier == 2).first()


def test_simulated_player_arrival_materializes_an_unvisited_minor_settlement(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)

    stub = _a_minor_settlement(db_session)
    assert stub is not None
    assert stub.materialization_tier == 2
    assert stub.description == ""

    player = player_simulation.SimulatedPlayer(
        campaign_id=campaign.id,
        name="Traveler",
        location_id=village.id,
        travel_destination_id=stub.id,
        travel_connection_id=None,
        travel_started_world_minute=0,
        travel_arrival_world_minute=100,
    )
    db_session.add(player)
    db_session.flush()

    completed = player_simulation._complete_travel_if_due(db_session, campaign.id, player, 100)

    assert completed is True
    db_session.refresh(stub)
    assert stub.materialization_tier == 1
    assert stub.description != ""
    assert player.location_id == stub.id
