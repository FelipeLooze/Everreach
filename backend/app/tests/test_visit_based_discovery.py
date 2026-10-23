from app.core.enums import (
    DiscoveryStatus,
    GeographicKnowledgeAspect,
    GeographicPrecision,
    KnowerType,
)
from app.db.models.location import Location, LocationConnection
from app.game.character.service import create_character
from app.game.discovery.service import (
    discover_connection,
    get_location_discovery,
    location_display_name,
    record_location_visit,
)
from app.game.knowledge.geography import (
    ensure_geographic_fact,
    geographic_fact_key,
    grant_fact_with_precision,
)
from app.game.map.view import get_map_view
from app.game.travel.service import move_character
from app.game.world.seed import create_campaign, seed_initial_region


def test_world_start_records_one_initial_visit_and_returns_canonical_name(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "S1.4 Start"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    response = client.post(
        f"/api/campaigns/{campaign['id']}/start", params={"character_id": character["id"]}
    )
    assert response.status_code == 200
    location = response.json()["state"]["location"]
    discovery = get_location_discovery(db_session, character["id"], location["id"])
    assert location["name"] is not None
    assert discovery.status == DiscoveryStatus.VISITED.value
    assert discovery.visit_count == 1
    assert discovery.visited_at == discovery.last_visited_at

    # The idempotent start endpoint must not invent another physical arrival.
    client.post(
        f"/api/campaigns/{campaign['id']}/start", params={"character_id": character["id"]}
    )
    db_session.refresh(discovery)
    assert discovery.visit_count == 1


def test_authoritative_travel_arrival_counts_revisits_and_traversed_routes(db_session):
    campaign = create_campaign(db_session, "S1.4 Travel")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    character.stamina_current = character.stamina_max = 100
    record_location_visit(db_session, character.id, village.id, source="test_start")
    outbound = db_session.query(LocationConnection).filter(
        LocationConnection.from_location_id == village.id,
        LocationConnection.active.is_(True),
    ).first()
    reverse = db_session.query(LocationConnection).filter(
        LocationConnection.from_location_id == outbound.to_location_id,
        LocationConnection.to_location_id == village.id,
        LocationConnection.active.is_(True),
    ).one()
    discover_connection(db_session, character.id, outbound.id)
    discover_connection(db_session, character.id, reverse.id)

    move_character(db_session, campaign.id, character, outbound.to_location_id)
    move_character(db_session, campaign.id, character, village.id)
    move_character(db_session, campaign.id, character, outbound.to_location_id)

    destination = get_location_discovery(db_session, character.id, outbound.to_location_id)
    assert destination.status == DiscoveryStatus.VISITED.value
    assert destination.visit_count == 2
    assert destination.last_visited_at >= destination.visited_at


def test_repeat_visit_updates_one_row_not_duplicate(db_session):
    campaign = create_campaign(db_session, "S1.4 Repeat")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    first, first_visit = record_location_visit(db_session, character.id, village.id, source="arrival:1")
    second, second_first = record_location_visit(db_session, character.id, village.id, source="arrival:2")
    assert first.id == second.id
    assert first_visit is True
    assert second_first is False
    assert second.visit_count == 2


def test_default_map_view_excludes_mentioned_but_unvisited_location(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "S1.4 Knowledge"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    start = client.post(
        f"/api/campaigns/{campaign['id']}/start", params={"character_id": character["id"]}
    ).json()
    region_id = start["state"]["region"]["id"]
    mentioned = Location(region_id=region_id, name="Arvendell", type="settlement", x=90, y=90)
    db_session.add(mentioned)
    db_session.flush()
    fact = ensure_geographic_fact(
        db_session,
        campaign["id"],
        "location",
        mentioned.id,
        GeographicKnowledgeAspect.EXISTENCE,
        "Arvendell existe ao norte.",
    )
    grant_fact_with_precision(
        db_session,
        campaign["id"],
        fact.fact_key,
        KnowerType.PLAYER,
        character["id"],
        precision=GeographicPrecision.VAGUE,
    )
    db_session.commit()

    normal = client.get(
        f"/api/campaigns/{campaign['id']}/map-view",
        params={"character_id": character["id"]},
    ).json()
    rich = client.get(
        f"/api/campaigns/{campaign['id']}/map-view",
        params={"character_id": character["id"], "include_unvisited_knowledge": True},
    ).json()
    assert mentioned.id not in {row["id"] for row in normal["locations"]}
    assert mentioned.id in {row["id"] for row in rich["locations"]}
    # Mentioned is known, not visited — so the default (visited-only) map
    # still leaves it out.
    assert get_location_discovery(db_session, character["id"], mentioned.id).status == "DISCOVERED"


def test_ordinary_visit_reveals_name_but_explicit_secret_identity_stays_masked(db_session):
    campaign = create_campaign(db_session, "S1.4 Secret")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    ordinary = Location(region_id=region.id, name="Casa do Moinho", type="building")
    secret = Location(
        region_id=region.id,
        name="Templo de Morgrin",
        type="ruins",
        identity_hidden=True,
        unrevealed_name="Ruínas desconhecidas",
    )
    db_session.add_all((ordinary, secret))
    db_session.flush()
    ordinary_discovery, _ = record_location_visit(
        db_session, character.id, ordinary.id, source="arrival:ordinary"
    )
    secret_discovery, _ = record_location_visit(
        db_session, character.id, secret.id, source="arrival:secret"
    )
    assert location_display_name(ordinary, ordinary_discovery) == ordinary.name
    assert location_display_name(secret, secret_discovery) == "Ruínas desconhecidas"

    ensure_geographic_fact(
        db_session,
        campaign.id,
        "location",
        secret.id,
        GeographicKnowledgeAspect.NAME,
        f"As ruínas são o {secret.name}.",
        is_secret=True,
    )
    grant_fact_with_precision(
        db_session,
        campaign.id,
        geographic_fact_key("location", secret.id, GeographicKnowledgeAspect.NAME),
        KnowerType.PLAYER,
        character.id,
        precision=GeographicPrecision.PRECISE,
    )
    view = get_map_view(db_session, campaign.id, character.id, visited_only=True)
    secret_entry = next(row for row in view.locations if row.id == secret.id)
    assert secret_entry.name == secret.name


def test_unvisited_discovery_status_does_not_enter_visited_map(db_session):
    campaign = create_campaign(db_session, "S1.4 Discovered Is Not Visited")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    record_location_visit(db_session, character.id, village.id, source="start")
    distant = db_session.query(Location).filter(
        Location.region_id == region.id, Location.id != village.id
    ).first()
    from app.game.discovery.service import set_location_discovery

    set_location_discovery(db_session, character.id, distant.id, DiscoveryStatus.DISCOVERED)
    view = get_map_view(db_session, campaign.id, character.id, visited_only=True)
    assert {row.id for row in view.locations} == {village.id}
