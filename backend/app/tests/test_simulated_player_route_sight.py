"""Transported people anywhere can see the routes leading out of where they
stand — not only in the starting village, whose routes were the only ones
with facts, which left everyone elsewhere stuck for good."""
import random

from app.core.enums import KnowerType, RiskTolerance, SimulatedPlayerArchetype
from app.db.models.character import Character
from app.db.models.location import LocationConnection
from app.db.models.simulated_player import SimulatedPlayer
from app.game.npcs.service import knows
from app.game.time import clock
from app.simulation import player_simulation


def test_a_transported_person_away_from_the_village_still_finds_a_way_out(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Route sight"}).json()
    character_data = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    client.post(f"/api/campaigns/{campaign['id']}/start", params={"character_id": character_data["id"]})
    village_id = db_session.get(Character, character_data["id"]).location_id
    elsewhere = (
        db_session.query(LocationConnection)
        .filter(LocationConnection.from_location_id == village_id)
        .first()
        .to_location_id
    )
    wanderer = SimulatedPlayer(
        campaign_id=campaign["id"], name="Ivo Tarn", location_id=elsewhere,
        archetype=SimulatedPlayerArchetype.EXPLORER, risk_tolerance=RiskTolerance.BOLD,
    )
    db_session.add(wanderer)
    db_session.flush()
    assert player_simulation._known_outgoing_connections(db_session, campaign["id"], wanderer) == []

    now = clock.get_world_time(db_session, campaign["id"]).total_minutes()
    started = player_simulation._try_start_travel(
        db_session, campaign["id"], wanderer, random.Random(1), now
    )

    assert started
    route = db_session.get(LocationConnection, wanderer.travel_connection_id)
    assert route.from_location_id == elsewhere
    assert knows(db_session, KnowerType.SIMULATED_PLAYER, wanderer.id, f"visible_route:{route.id}", campaign["id"])


def test_a_wanderer_stays_a_few_days_before_leaving_again(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Route pacing"}).json()
    character_data = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    client.post(f"/api/campaigns/{campaign['id']}/start", params={"character_id": character_data["id"]})
    village_id = db_session.get(Character, character_data["id"]).location_id
    wanderer = SimulatedPlayer(
        campaign_id=campaign["id"], name="Ivo Tarn", location_id=village_id,
        archetype=SimulatedPlayerArchetype.EXPLORER, risk_tolerance=RiskTolerance.BOLD,
    )
    db_session.add(wanderer)
    db_session.flush()
    now = clock.get_world_time(db_session, campaign["id"]).total_minutes()
    assert player_simulation._try_start_travel(db_session, campaign["id"], wanderer, random.Random(1), now)
    player_simulation._complete_travel_if_due(db_session, campaign["id"], wanderer, wanderer.travel_arrival_world_minute)

    soon = now + 24 * 60
    later = now + player_simulation.MIN_MINUTES_BETWEEN_DEPARTURES
    assert not player_simulation._try_start_travel(db_session, campaign["id"], wanderer, random.Random(1), soon)
    assert player_simulation._try_start_travel(db_session, campaign["id"], wanderer, random.Random(1), later)
