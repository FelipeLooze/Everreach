from app.core.enums import DiscoveryStatus
from app.db.models.location import CharacterLocationDiscovery
from app.game.character.service import create_character
from app.game.discovery.service import (
    get_location_discovery,
    set_location_discovery,
)
from app.game.world.seed import create_campaign, seed_initial_region


def test_location_discovery_is_individual_per_character(db_session):
    campaign = create_campaign(db_session, "Discovery Test")
    region, village = seed_initial_region(db_session, campaign.id)

    first = create_character(
        db_session,
        campaign.id,
        "First",
        region.id,
        village.id,
    )

    second = create_character(
        db_session,
        campaign.id,
        "Second",
        region.id,
        village.id,
    )

    set_location_discovery(
        db_session,
        first.id,
        village.id,
        DiscoveryStatus.VISITED,
    )

    first_discovery = get_location_discovery(
        db_session,
        first.id,
        village.id,
    )

    second_discovery = get_location_discovery(
        db_session,
        second.id,
        village.id,
    )

    assert first_discovery is not None
    assert first_discovery.status == DiscoveryStatus.VISITED
    assert second_discovery is None


def test_location_discovery_only_moves_forward(db_session):
    campaign = create_campaign(db_session, "Discovery Progression")
    region, village = seed_initial_region(db_session, campaign.id)

    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        village.id,
    )

    discovery, changed = set_location_discovery(
        db_session,
        character.id,
        village.id,
        DiscoveryStatus.RUMORED,
    )

    assert changed is True
    assert discovery.status == DiscoveryStatus.RUMORED
    assert discovery.discovered_at is None
    assert discovery.visited_at is None

    discovery, changed = set_location_discovery(
        db_session,
        character.id,
        village.id,
        DiscoveryStatus.VISITED,
    )

    assert changed is True
    assert discovery.status == DiscoveryStatus.VISITED
    assert discovery.discovered_at is not None
    assert discovery.visited_at is not None

    discovery, changed = set_location_discovery(
        db_session,
        character.id,
        village.id,
        DiscoveryStatus.DISCOVERED,
    )

    assert changed is False
    assert discovery.status == DiscoveryStatus.VISITED

    discovery, changed = set_location_discovery(
        db_session,
        character.id,
        village.id,
        DiscoveryStatus.MAPPED,
    )

    assert changed is True
    assert discovery.status == DiscoveryStatus.MAPPED
    assert discovery.mapped_at is not None


def test_world_start_marks_initial_location_as_visited(
    client,
    db_session,
):
    campaign = client.post(
        "/api/campaigns",
        json={"name": "Arrival Discovery"},
    ).json()

    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters",
        json={"name": "Hero"},
    ).json()

    response = client.post(
        f"/api/campaigns/{campaign['id']}/start",
        params={"character_id": character["id"]},
    )

    assert response.status_code == 200

    location_id = response.json()["state"]["location"]["id"]

    discovery = (
        db_session.query(CharacterLocationDiscovery)
        .filter(
            CharacterLocationDiscovery.character_id == character["id"],
            CharacterLocationDiscovery.location_id == location_id,
        )
        .one()
    )

    assert discovery.status == DiscoveryStatus.VISITED
    assert discovery.discovered_at is not None
    assert discovery.visited_at is not None