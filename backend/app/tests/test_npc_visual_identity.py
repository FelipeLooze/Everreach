"""Phase 21E — NPC Visual Identity."""

from app.db.models.npc import NPC
from app.game.visual.npc import (
    NPCVisualIdentityError,
    get_npc_visual_spec,
    resolve_npc_appearance,
    resolve_npc_stable_and_current,
    set_npc_current_appearance,
    set_npc_stable_identity,
)
from app.game.visual.spec import set_stable_visual_traits
from app.game.world.seed import create_campaign, seed_initial_region

import pytest


def _npc(db_session, campaign_id, region_id, location_id, name="Mira"):
    npc = NPC(campaign_id=campaign_id, region_id=region_id, location_id=location_id, name=name, role="ferreira")
    db_session.add(npc)
    db_session.flush()
    return npc


def test_stable_traits_merge_and_never_lose_earlier_permanent_facts(db_session):
    campaign = create_campaign(db_session, "NPC Visual Estavel", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)

    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "red", "eye_color": "green"})
    spec = set_npc_stable_identity(db_session, campaign.id, npc.id, {"permanent_scar": "left cheek"})

    assert spec.stable == {"hair_color": "red", "eye_color": "green", "permanent_scar": "left cheek"}


def test_current_appearance_changes_without_touching_stable_identity(db_session):
    campaign = create_campaign(db_session, "NPC Visual Atual", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "red"})

    spec = set_npc_current_appearance(db_session, campaign.id, npc.id, {"clothing": "work clothes"})

    assert spec.current == {"clothing": "work clothes"}
    assert spec.stable == {"hair_color": "red"}


def test_get_npc_visual_spec_is_isolated_per_npc(db_session):
    campaign = create_campaign(db_session, "NPC Visual Isolado", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    mira = _npc(db_session, campaign.id, region.id, village.id, name="Mira")
    logan = _npc(db_session, campaign.id, region.id, village.id, name="Logan")
    set_npc_stable_identity(db_session, campaign.id, mira.id, {"hair_color": "red"})

    assert get_npc_visual_spec(db_session, campaign.id, mira.id).stable == {"hair_color": "red"}
    assert get_npc_visual_spec(db_session, campaign.id, logan.id).stable == {}


def test_resolve_npc_appearance_lets_personal_stable_override_regional_tendency(db_session):
    campaign = create_campaign(db_session, "NPC Visual Regiao Sobrescrita", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_stable_visual_traits(
        db_session, "region", region.id, {"clothing_material": "wool and linen"}, campaign_id=campaign.id,
    )
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"clothing_material": "ceremonial silk"})

    resolved = resolve_npc_appearance(db_session, campaign.id, npc.id)

    assert resolved["clothing_material"] == "ceremonial silk"


def test_resolve_npc_appearance_lets_current_state_override_stable_identity(db_session):
    campaign = create_campaign(db_session, "NPC Visual Estado Sobrescreve", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"clothing": "everyday tunic"})
    set_npc_current_appearance(db_session, campaign.id, npc.id, {"clothing": "black cloak"})

    resolved = resolve_npc_appearance(db_session, campaign.id, npc.id)

    assert resolved["clothing"] == "black cloak"


def test_resolve_npc_appearance_falls_back_to_regional_tendency_with_no_personal_override(db_session):
    campaign = create_campaign(db_session, "NPC Visual So Regiao", world_seed=6)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_stable_visual_traits(
        db_session, "region", region.id, {"clothing_material": "wool and linen"}, campaign_id=campaign.id,
    )

    resolved = resolve_npc_appearance(db_session, campaign.id, npc.id)

    assert resolved["clothing_material"] == "wool and linen"


def test_raises_for_a_nonexistent_npc(db_session):
    campaign = create_campaign(db_session, "NPC Visual Inexistente", world_seed=7)

    with pytest.raises(NPCVisualIdentityError):
        resolve_npc_appearance(db_session, campaign.id, "npc_nao_existe")


def test_resolve_npc_stable_and_current_keeps_the_two_halves_separate(db_session):
    campaign = create_campaign(db_session, "NPC Visual Stable Current Separado", world_seed=8)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "silver"})
    set_npc_current_appearance(db_session, campaign.id, npc.id, {"clothing": "travel cloak"})

    stable, current = resolve_npc_stable_and_current(db_session, campaign.id, npc.id)

    assert stable == {"hair_color": "silver"}
    assert current == {"clothing": "travel cloak"}


def test_resolve_npc_stable_and_current_includes_regional_tendency_in_stable(db_session):
    campaign = create_campaign(db_session, "NPC Visual Stable Regional", world_seed=9)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = _npc(db_session, campaign.id, region.id, village.id)
    set_stable_visual_traits(
        db_session, "region", region.id, {"clothing_material": "wool and linen"}, campaign_id=campaign.id,
    )

    stable, current = resolve_npc_stable_and_current(db_session, campaign.id, npc.id)

    assert stable["clothing_material"] == "wool and linen"
    assert current == {}


def test_resolve_npc_stable_and_current_raises_for_a_nonexistent_npc(db_session):
    campaign = create_campaign(db_session, "NPC Visual Stable Current Inexistente", world_seed=10)

    with pytest.raises(NPCVisualIdentityError):
        resolve_npc_stable_and_current(db_session, campaign.id, "npc_nao_existe")
