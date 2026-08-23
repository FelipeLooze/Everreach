"""Phase 20I — Settlement & City Maps."""

from app.core.enums import DiscoveryStatus
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def test_knowing_a_settlement_does_not_reveal_its_districts(db_session):
    campaign = create_campaign(db_session, "Arven Sem Distritos", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    district = Location(
        region_id=region.id, parent_location_id=village.id, name="Distrito Comercial", type="district",
    )
    db_session.add(district)
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    # `district` nunca recebe seu próprio CharacterLocationDiscovery.

    view = get_map_view(db_session, campaign.id, character.id)

    assert any(item.id == village.id for item in view.locations)
    assert all(item.id != district.id for item in view.locations)


def test_settlement_scope_shows_only_known_districts_of_that_settlement(db_session):
    campaign = create_campaign(db_session, "Escopo Assentamento", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    gate = Location(
        region_id=region.id, parent_location_id=village.id, name="Portao Sul", type="district",
    )
    market = Location(
        region_id=region.id, parent_location_id=village.id, name="Mercado", type="district",
    )
    other_settlement = Location(region_id=region.id, name="Outro Povoado", type="settlement")
    db_session.add_all([gate, market, other_settlement])
    db_session.flush()
    unrelated_district = Location(
        region_id=region.id, parent_location_id=other_settlement.id, name="Distrito Alheio", type="district",
    )
    db_session.add(unrelated_district)
    db_session.flush()

    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, gate.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, other_settlement.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, unrelated_district.id, DiscoveryStatus.VISITED)
    # `market` nunca é descoberto.

    view = get_map_view(db_session, campaign.id, character.id, scope=f"settlement:{village.id}")

    location_ids = {item.id for item in view.locations}
    assert location_ids == {gate.id}


def test_settlement_scope_for_a_settlement_with_no_known_districts_returns_nothing(db_session):
    campaign = create_campaign(db_session, "Assentamento Sem Distrito Conhecido", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id, scope=f"settlement:{village.id}")

    assert view.locations == []
    assert view.regions == []


def test_first_arrival_district_becomes_visible_once_individually_discovered(db_session):
    campaign = create_campaign(db_session, "Primeira Chegada", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    main_road = Location(
        region_id=region.id, parent_location_id=village.id, name="Avenida Principal", type="district",
    )
    db_session.add(main_road)
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, main_road.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id, scope=f"settlement:{village.id}")

    assert {item.id for item in view.locations} == {main_road.id}
