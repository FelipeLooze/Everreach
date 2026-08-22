"""Phase 15L — Regional Threats, Wildlife & Ecology.

Every subregion gets exactly one threat/ecology entry — a population/
habitat abstraction, never an individual creature instance. The anchor
subregion's threat is fixed (boars from the already-existing forest near
Cardal), mirroring the spec's own worked example.
"""

from app.core.enums import ThreatIntensity
from app.db.models.regional_threat import RegionalThreat
from app.db.models.subregion import Subregion
from app.game.world.content_pools import ANCHOR_SUBREGION_NAME
from app.game.world.seed import create_campaign, seed_initial_region


def test_every_subregion_gets_exactly_one_threat(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = db_session.query(Subregion).filter(Subregion.region_id == region.id).all()
    for subregion in subregions:
        threats = (
            db_session.query(RegionalThreat)
            .filter(RegionalThreat.subregion_id == subregion.id)
            .all()
        )
        assert len(threats) == 1


def test_anchor_subregion_gets_the_fixed_boar_threat(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    anchor = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == region.id, Subregion.name == ANCHOR_SUBREGION_NAME)
        .one()
    )
    threat = db_session.query(RegionalThreat).filter(RegionalThreat.subregion_id == anchor.id).one()

    assert threat.threat_type == "BOARS"
    assert "Cardal" in threat.description


def test_threat_intensity_matches_subregion_danger_level(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = db_session.query(Subregion).filter(Subregion.region_id == region.id).all()
    for subregion in subregions:
        threat = db_session.query(RegionalThreat).filter(RegionalThreat.subregion_id == subregion.id).one()
        if subregion.danger_level in ("SAFE", "LOW"):
            assert threat.intensity == ThreatIntensity.LOW
        elif subregion.danger_level == "MODERATE":
            assert threat.intensity == ThreatIntensity.MODERATE
        else:
            assert threat.intensity == ThreatIntensity.HIGH
