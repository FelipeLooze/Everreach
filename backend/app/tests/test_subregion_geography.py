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


def test_every_non_anchor_subregion_gets_a_geography_feature(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = db_session.query(Subregion).filter(Subregion.region_id == region.id).all()
    non_anchor = [s for s in subregions if s.name != ANCHOR_SUBREGION_NAME]

    for subregion in non_anchor:
        features = (
            db_session.query(Location)
            .filter(Location.subregion_id == subregion.id)
            .all()
        )
        assert len(features) == 1
        expected_names = {name for name, _type, _desc in GEOGRAPHY_BY_BIOME[str(subregion.biome)]}
        assert features[0].name in expected_names
        expected_types = {loc_type for _name, loc_type, _desc in GEOGRAPHY_BY_BIOME[str(subregion.biome)]}
        assert features[0].type in expected_types


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
    feature = db_session.query(Location).filter(Location.subregion_id == non_anchor.id).one()

    from app.core.enums import DiscoveryStatus

    assert feature.discovery_status == DiscoveryStatus.UNKNOWN
