"""Phase 21G — Location Visual Identity."""

import pytest

from app.game.visual.location import (
    LocationVisualIdentityError,
    get_location_visual_spec,
    resolve_location_visual,
    set_location_current_scene,
    set_location_stable_identity,
)
from app.game.visual.spec import set_stable_visual_traits
from app.game.world.seed import create_campaign, seed_initial_region


def test_stable_and_current_scene_are_separate_and_merge_independently(db_session):
    campaign = create_campaign(db_session, "Local Estavel E Cena", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    set_location_stable_identity(
        db_session, campaign.id, village.id, {"construction": "stone and wood workshop"},
    )
    set_location_current_scene(db_session, campaign.id, village.id, {"weather": "rain", "time": "night"})

    spec = get_location_visual_spec(db_session, campaign.id, village.id)

    assert spec.stable == {"construction": "stone and wood workshop"}
    assert spec.current == {"weather": "rain", "time": "night"}


def test_resolve_location_visual_inherits_region_tendency(db_session):
    campaign = create_campaign(db_session, "Local Herda Regiao", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    set_stable_visual_traits(
        db_session, "region", region.id, {"architecture": "timber and thatch"}, campaign_id=campaign.id,
    )

    resolved = resolve_location_visual(db_session, campaign.id, village.id)

    assert resolved["architecture"] == "timber and thatch"


def test_resolve_location_visual_lets_subregion_override_region(db_session):
    campaign = create_campaign(db_session, "Local Subregiao Sobrescreve", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    set_stable_visual_traits(
        db_session, "region", region.id, {"vegetation": "grassland"}, campaign_id=campaign.id,
    )
    set_stable_visual_traits(
        db_session, "subregion", village.subregion_id, {"vegetation": "dense pine forest"}, campaign_id=campaign.id,
    )

    resolved = resolve_location_visual(db_session, campaign.id, village.id)

    assert resolved["vegetation"] == "dense pine forest"


def test_resolve_location_visual_lets_explicit_location_canon_override_broader_defaults(db_session):
    campaign = create_campaign(db_session, "Local Canon Explicito Sobrescreve", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    set_stable_visual_traits(
        db_session, "region", region.id, {"construction": "modest timber"}, campaign_id=campaign.id,
    )
    set_location_stable_identity(db_session, campaign.id, village.id, {"construction": "ceremonial stone hall"})

    resolved = resolve_location_visual(db_session, campaign.id, village.id)

    assert resolved["construction"] == "ceremonial stone hall"


def test_current_scene_overrides_stable_identity_for_the_same_key(db_session):
    campaign = create_campaign(db_session, "Local Cena Sobrescreve Estavel", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    set_location_stable_identity(db_session, campaign.id, village.id, {"forge_state": "cold"})
    set_location_current_scene(db_session, campaign.id, village.id, {"forge_state": "active"})

    resolved = resolve_location_visual(db_session, campaign.id, village.id)

    assert resolved["forge_state"] == "active"


def test_raises_for_a_nonexistent_location(db_session):
    campaign = create_campaign(db_session, "Local Inexistente", world_seed=6)

    with pytest.raises(LocationVisualIdentityError):
        resolve_location_visual(db_session, campaign.id, "loc_nao_existe")
