"""Phase 21H — Settlement Visual Identity."""

import pytest

from app.core.enums import SettlementType
from app.db.models.location import Location
from app.db.models.settlement import Settlement
from app.game.visual.settlement import (
    SettlementVisualIdentityError,
    resolve_settlement_visual,
    set_settlement_current_scene,
    set_settlement_stable_identity,
)
from app.game.visual.spec import set_stable_visual_traits
from app.game.world.seed import create_campaign, seed_initial_region


def _settlement(db_session, region_id, name, settlement_type=SettlementType.VILLAGE, population_tier=1):
    """A fresh Location + Settlement pair — seed_initial_region's own
    village already has its own Settlement row, so tests must not
    reuse that location_id (Settlement.location_id is unique)."""
    location = Location(region_id=region_id, name=name, type="settlement")
    db_session.add(location)
    db_session.flush()
    settlement = Settlement(
        location_id=location.id, settlement_type=settlement_type, population_tier=population_tier,
    )
    db_session.add(settlement)
    db_session.flush()
    return settlement


def test_scale_always_reflects_real_canon_settlement_type(db_session):
    campaign = create_campaign(db_session, "Assentamento Escala", world_seed=1)
    region, _village = seed_initial_region(db_session, campaign.id)
    arven = _settlement(db_session, region.id, "Arven", SettlementType.MAJOR_CITY, population_tier=5)

    resolved = resolve_settlement_visual(db_session, campaign.id, arven.id)

    assert resolved["settlement_scale"] == SettlementType.MAJOR_CITY.value
    assert resolved["population_tier"] == 5


def test_a_village_and_a_major_city_resolve_different_scale_without_any_manual_canon(db_session):
    campaign = create_campaign(db_session, "Assentamento Escalas Diferentes", world_seed=2)
    region, _village = seed_initial_region(db_session, campaign.id)
    cardal = _settlement(db_session, region.id, "Cardal", SettlementType.VILLAGE)
    arven = _settlement(db_session, region.id, "Arven", SettlementType.MAJOR_CITY)

    assert resolve_settlement_visual(db_session, campaign.id, cardal.id)["settlement_scale"] == "VILLAGE"
    assert resolve_settlement_visual(db_session, campaign.id, arven.id)["settlement_scale"] == "MAJOR_CITY"


def test_settlement_inherits_its_underlying_locations_regional_tendency(db_session):
    campaign = create_campaign(db_session, "Assentamento Herda Regiao", world_seed=3)
    region, _village = seed_initial_region(db_session, campaign.id)
    settlement = _settlement(db_session, region.id, "Rowan")
    set_stable_visual_traits(
        db_session, "region", region.id, {"architecture": "timber and thatch"}, campaign_id=campaign.id,
    )

    resolved = resolve_settlement_visual(db_session, campaign.id, settlement.id)

    assert resolved["architecture"] == "timber and thatch"


def test_settlement_specific_canon_overrides_the_mandatory_scale_default(db_session):
    campaign = create_campaign(db_session, "Assentamento Canon Sobrescreve Escala", world_seed=4)
    region, _village = seed_initial_region(db_session, campaign.id)
    settlement = _settlement(db_session, region.id, "Cardal", SettlementType.VILLAGE)
    set_settlement_stable_identity(db_session, campaign.id, settlement.id, {"purpose": "agricultural"})

    resolved = resolve_settlement_visual(db_session, campaign.id, settlement.id)

    assert resolved["purpose"] == "agricultural"
    assert resolved["settlement_scale"] == "VILLAGE"


def test_current_scene_overrides_stable_settlement_identity(db_session):
    campaign = create_campaign(db_session, "Assentamento Cena Sobrescreve", world_seed=5)
    region, _village = seed_initial_region(db_session, campaign.id)
    settlement = _settlement(db_session, region.id, "Rowan")
    set_settlement_stable_identity(db_session, campaign.id, settlement.id, {"activity": "quiet"})
    set_settlement_current_scene(db_session, campaign.id, settlement.id, {"activity": "market day, crowded"})

    resolved = resolve_settlement_visual(db_session, campaign.id, settlement.id)

    assert resolved["activity"] == "market day, crowded"


def test_raises_for_a_nonexistent_settlement(db_session):
    campaign = create_campaign(db_session, "Assentamento Inexistente", world_seed=6)

    with pytest.raises(SettlementVisualIdentityError):
        resolve_settlement_visual(db_session, campaign.id, "settlement_nao_existe")
