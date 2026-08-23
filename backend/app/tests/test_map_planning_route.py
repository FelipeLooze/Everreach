"""Phase 20M — Travel Planning Integration (API route)."""

from app.core.enums import DiscoveryStatus
from app.db.models.location import Location, LocationConnection
from app.game.character.service import create_character
from app.game.discovery.service import discover_connection, set_location_discovery
from app.game.world.seed import create_campaign, seed_initial_region


def test_route_plan_endpoint_returns_a_known_route(client, db_session):
    campaign = create_campaign(db_session, "Rota Api Conhecida", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    arven = Location(region_id=region.id, name="Arven", type="settlement", x=2, y=2)
    db_session.add(arven)
    db_session.flush()
    connection = LocationConnection(from_location_id=village.id, to_location_id=arven.id, distance=5.0, danger=1)
    db_session.add(connection)
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, arven.id, DiscoveryStatus.VISITED)
    discover_connection(db_session, character.id, connection.id)
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/route-plan",
        params={"character_id": character.id, "from_location_id": village.id, "to_location_id": arven.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["known"] is True
    assert len(body["segments"]) == 1
    assert body["total_distance"] == 5.0


def test_route_plan_endpoint_says_no_known_route_instead_of_erroring(client, db_session):
    campaign = create_campaign(db_session, "Rota Api Desconhecida", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    arven = Location(region_id=region.id, name="Arven", type="settlement", x=2, y=2)
    db_session.add(arven)
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, arven.id, DiscoveryStatus.VISITED)
    # Nenhuma conexão descoberta entre os dois.
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/route-plan",
        params={"character_id": character.id, "from_location_id": village.id, "to_location_id": arven.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["known"] is False
    assert body["segments"] == []
