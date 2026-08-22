"""Phase 15Q — Region Validation & Persistence.

validate_region_package is an independent consistency pass, not a trust
exercise in the generator's own bookkeeping — it re-derives each
invariant from what actually got persisted. A normally-generated region
always passes; each test below corrupts one specific invariant to prove
the corresponding check actually fires (not just that some assertion
somewhere would eventually catch it).
"""

import pytest

from app.db.models.location import Location
from app.db.models.organization import Organization
from app.game.world.seed import create_campaign, seed_initial_region
from app.game.world.validation import RegionValidationError, validate_region_package


def test_a_normally_generated_region_passes_validation(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    validate_region_package(db_session, region)  # must not raise


def test_validation_rejects_duplicate_location_names(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)

    impostor = Location(region_id=region.id, name=village.name, type="village")
    db_session.add(impostor)
    db_session.flush()

    with pytest.raises(RegionValidationError, match="duplicados"):
        validate_region_package(db_session, region)


def test_validation_rejects_an_organization_headquartered_outside_the_region(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    other_campaign = create_campaign(db_session, "Outra Campanha")
    _other_region, other_village = seed_initial_region(db_session, other_campaign.id)

    organization = db_session.query(Organization).filter(Organization.campaign_id == campaign.id).first()
    assert organization is not None
    organization.headquarters_location_id = other_village.id  # a real Location, just not in this Region
    db_session.flush()

    with pytest.raises(RegionValidationError, match="headquarters_location_id"):
        validate_region_package(db_session, region)


def test_validation_rejects_a_region_with_skeleton_not_complete(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    region.skeleton_complete = False
    db_session.flush()

    with pytest.raises(RegionValidationError, match="skeleton_complete"):
        validate_region_package(db_session, region)
