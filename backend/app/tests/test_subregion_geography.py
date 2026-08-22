"""Phase 15E — Geography & Biomes.

Every non-anchor subregion gets one major physical geography feature
matching its own biome, as a real Location — persistent world truth that
exists whether or not the protagonist has ever been near it. The anchor
subregion keeps its bespoke, hand-authored geography from the original
seed (forest edge, creek, clearing) instead of also getting a generated
feature layered on top.
"""

from app.db.models.location import Location
from app.db.models.subregion import Subregion
from app.game.world.content_pools import ANCHOR_SUBREGION_NAME, GEOGRAPHY_BY_BIOME
from app.game.world.seed import create_campaign, seed_initial_region

ALL_GEOGRAPHY_NAMES = {name for pool in GEOGRAPHY_BY_BIOME.values() for name, _type, _desc in pool}
ALL_GEOGRAPHY_TYPES = {loc_type for pool in GEOGRAPHY_BY_BIOME.values() for _name, loc_type, _desc in pool}


def _geography_locations(db_session, subregion_id):
    return [
        loc
        for loc in db_session.query(Location).filter(Location.subregion_id == subregion_id).all()
        if loc.name in ALL_GEOGRAPHY_NAMES
    ]


def test_every_non_anchor_subregion_gets_a_geography_feature(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = db_session.query(Subregion).filter(Subregion.region_id == region.id).all()
    non_anchor = [s for s in subregions if s.name != ANCHOR_SUBREGION_NAME]

    for subregion in non_anchor:
        features = _geography_locations(db_session, subregion.id)
        assert len(features) == 1
        assert features[0].type in ALL_GEOGRAPHY_TYPES


def test_anchor_subregion_keeps_its_bespoke_geography_only(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    anchor = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == region.id, Subregion.name == ANCHOR_SUBREGION_NAME)
        .one()
    )
    anchor_location_names = {
        loc.name
        for loc in db_session.query(Location).filter(Location.subregion_id == anchor.id).all()
    }

    assert anchor_location_names == {
        "Cardal",
        "Bosque da Beira do Vale",
        "Estrada do Moinho",
        "Riacho Negro",
        "Clareira do Vidro Antigo",
    }


def test_geography_features_exist_regardless_of_player_discovery(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = db_session.query(Subregion).filter(Subregion.region_id == region.id).all()
    non_anchor = next(s for s in subregions if s.name != ANCHOR_SUBREGION_NAME)
    [feature] = _geography_locations(db_session, non_anchor.id)

    from app.core.enums import DiscoveryStatus

    assert feature.discovery_status == DiscoveryStatus.UNKNOWN
