"""Phase 21I — Regional Visual Identity."""

import pytest

from app.game.visual.region import (
    RegionalVisualIdentityError,
    get_region_visual_spec,
    get_subregion_visual_spec,
    resolve_subregion_visual,
    set_region_visual_identity,
    set_subregion_current_state,
    set_subregion_visual_identity,
)
from app.game.world.seed import create_campaign, seed_initial_region


def test_region_visual_identity_is_set_and_read_back(db_session):
    campaign = create_campaign(db_session, "Regiao Identidade", world_seed=1)
    region, _village = seed_initial_region(db_session, campaign.id)

    set_region_visual_identity(db_session, campaign.id, region.id, {"architecture": "timber and thatch"})

    assert get_region_visual_spec(db_session, campaign.id, region.id).stable == {
        "architecture": "timber and thatch",
    }


def test_subregion_visual_identity_overrides_regional_tendency(db_session):
    campaign = create_campaign(db_session, "Subregiao Sobrescreve Regiao", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    set_region_visual_identity(db_session, campaign.id, region.id, {"vegetation": "grassland"})
    set_subregion_visual_identity(
        db_session, campaign.id, village.subregion_id, {"vegetation": "dense pine forest"},
    )

    resolved = resolve_subregion_visual(db_session, campaign.id, village.subregion_id)

    assert resolved["vegetation"] == "dense pine forest"


def test_subregion_with_no_override_falls_back_to_regional_tendency(db_session):
    campaign = create_campaign(db_session, "Subregiao Sem Override", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    set_region_visual_identity(db_session, campaign.id, region.id, {"architecture": "timber and thatch"})

    resolved = resolve_subregion_visual(db_session, campaign.id, village.subregion_id)

    assert resolved["architecture"] == "timber and thatch"


def test_subregion_current_state_overrides_its_own_stable_identity(db_session):
    campaign = create_campaign(db_session, "Subregiao Estado Sobrescreve", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    set_subregion_visual_identity(db_session, campaign.id, village.subregion_id, {"season_feel": "spring bloom"})
    set_subregion_current_state(db_session, campaign.id, village.subregion_id, {"season_feel": "autumn decay"})

    resolved = resolve_subregion_visual(db_session, campaign.id, village.subregion_id)

    assert resolved["season_feel"] == "autumn decay"


def test_two_subregions_of_the_same_region_can_differ_meaningfully(db_session):
    """Regions are not mere biome palette swaps — different Subregions
    of the same Region can look meaningfully different (spec)."""
    campaign = create_campaign(db_session, "Subregioes Diferentes", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    other_subregion_spec = get_subregion_visual_spec(db_session, campaign.id, "subregion_outra")
    assert other_subregion_spec.stable == {}
    set_subregion_visual_identity(db_session, campaign.id, village.subregion_id, {"terrain": "rolling hills"})

    resolved_village = resolve_subregion_visual(db_session, campaign.id, village.subregion_id)

    assert resolved_village["terrain"] == "rolling hills"


def test_raises_for_a_nonexistent_subregion(db_session):
    campaign = create_campaign(db_session, "Subregiao Inexistente", world_seed=6)

    with pytest.raises(RegionalVisualIdentityError):
        resolve_subregion_visual(db_session, campaign.id, "subregion_nao_existe")
