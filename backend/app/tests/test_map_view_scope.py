"""Phase 20E — Hierarchical Map Levels (scope filtering)."""

from app.core.enums import DiscoveryStatus
from app.db.models.location import Location
from app.db.models.subregion import Subregion
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def _second_known_region(db_session, campaign_id, character_id):
    from app.db.models.region import Region

    region = Region(campaign_id=campaign_id, name="Outra Regiao")
    db_session.add(region)
    db_session.flush()
    location = Location(region_id=region.id, name="Posto Distante", type="generic")
    db_session.add(location)
    db_session.flush()
    set_location_discovery(db_session, character_id, location.id, DiscoveryStatus.VISITED)
    return region, location


def test_no_scope_returns_every_known_region_and_location(db_session):
    campaign = create_campaign(db_session, "Escopo Nenhum", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    other_region, other_location = _second_known_region(db_session, campaign.id, character.id)

    view = get_map_view(db_session, campaign.id, character.id)

    region_ids = {r.id for r in view.regions}
    assert region.id in region_ids
    assert other_region.id in region_ids
    location_ids = {l.id for l in view.locations}
    assert village.id in location_ids
    assert other_location.id in location_ids


def test_world_scope_returns_regions_but_no_location_detail(db_session):
    campaign = create_campaign(db_session, "Escopo Mundo", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id, scope="world")

    assert any(r.id == region.id for r in view.regions)
    assert view.locations == []


def test_region_scope_filters_to_one_region_only(db_session):
    campaign = create_campaign(db_session, "Escopo Regiao", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    other_region, other_location = _second_known_region(db_session, campaign.id, character.id)

    view = get_map_view(db_session, campaign.id, character.id, scope=f"region:{region.id}")

    assert {r.id for r in view.regions} == {region.id}
    assert {l.id for l in view.locations} == {village.id}


def test_region_scope_for_an_unknown_region_returns_nothing(db_session):
    campaign = create_campaign(db_session, "Escopo Regiao Desconhecida", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id, scope="region:region_nao_conhecida")

    assert view.regions == []
    assert view.locations == []


def test_subregion_scope_filters_locations_within_it(db_session):
    campaign = create_campaign(db_session, "Escopo Subregiao", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    subregion = Subregion(region_id=region.id, name="Vale Norte")
    db_session.add(subregion)
    db_session.flush()
    village.subregion_id = subregion.id
    other_location = Location(region_id=region.id, name="Fora Da Subregiao", type="generic")
    db_session.add(other_location)
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, other_location.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id, scope=f"subregion:{subregion.id}")

    assert {l.id for l in view.locations} == {village.id}


def test_subregion_scope_for_an_unknown_subregion_returns_nothing(db_session):
    campaign = create_campaign(db_session, "Escopo Subregiao Desconhecida", world_seed=6)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id, scope="subregion:subregion_desconhecida")

    assert view.regions == []
    assert view.locations == []


def test_unrecognized_scope_returns_nothing_rather_than_falling_back(db_session):
    campaign = create_campaign(db_session, "Escopo Invalido", world_seed=7)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id, scope="settlement:whatever")

    assert view.regions == []
    assert view.locations == []
