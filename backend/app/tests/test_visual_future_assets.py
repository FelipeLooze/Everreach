"""Phase 21Q — Future Generated-Asset Compatibility.

set_visual_asset_reference is a generic, opaque slot shared by every
subject_kind via the same VisualIdentity table 21C established — no
ComfyUI path/URL shape is assumed anywhere here, and `reference` is
never parsed, only stored and returned as-is.
"""

import pytest

from app.game.visual.spec import (
    FUTURE_ASSET_KINDS,
    FutureAssetKindError,
    get_visual_spec,
    set_stable_visual_traits,
    set_visual_asset_reference,
)
from app.game.world.seed import create_campaign


def test_asset_reference_is_absent_until_explicitly_set(db_session):
    campaign = create_campaign(db_session, "Visual Assets Ausente", world_seed=101)

    spec = get_visual_spec(db_session, "npc", "npc_mira", campaign_id=campaign.id)

    assert spec.assets == {}


def test_set_visual_asset_reference_records_an_opaque_reference(db_session):
    campaign = create_campaign(db_session, "Visual Assets Definido", world_seed=102)

    spec = set_visual_asset_reference(
        db_session, "npc", "npc_mira", "NPC_PORTRAIT", "asset_mira_portrait_v1",
        campaign_id=campaign.id,
    )

    assert spec.assets == {"NPC_PORTRAIT": "asset_mira_portrait_v1"}
    assert get_visual_spec(db_session, "npc", "npc_mira", campaign_id=campaign.id).assets == {
        "NPC_PORTRAIT": "asset_mira_portrait_v1",
    }


def test_set_visual_asset_reference_merges_rather_than_replaces(db_session):
    campaign = create_campaign(db_session, "Visual Assets Mescla", world_seed=103)
    set_visual_asset_reference(
        db_session, "npc", "npc_mira", "NPC_PORTRAIT", "asset_portrait",
        campaign_id=campaign.id,
    )

    spec = set_visual_asset_reference(
        db_session, "npc", "npc_mira", "NPC_FULL_BODY", "asset_full_body",
        campaign_id=campaign.id,
    )

    assert spec.assets == {"NPC_PORTRAIT": "asset_portrait", "NPC_FULL_BODY": "asset_full_body"}


def test_set_visual_asset_reference_with_none_clears_the_kind(db_session):
    campaign = create_campaign(db_session, "Visual Assets Limpa", world_seed=104)
    set_visual_asset_reference(
        db_session, "npc", "npc_mira", "NPC_PORTRAIT", "asset_stale",
        campaign_id=campaign.id,
    )

    spec = set_visual_asset_reference(
        db_session, "npc", "npc_mira", "NPC_PORTRAIT", None,
        campaign_id=campaign.id,
    )

    assert spec.assets == {}


def test_set_visual_asset_reference_never_touches_stable_or_current(db_session):
    campaign = create_campaign(db_session, "Visual Assets Isolado", world_seed=105)
    set_stable_visual_traits(
        db_session, "npc", "npc_mira", {"hair_color": "red"}, campaign_id=campaign.id,
    )

    spec = set_visual_asset_reference(
        db_session, "npc", "npc_mira", "NPC_PORTRAIT", "asset_portrait",
        campaign_id=campaign.id,
    )

    assert spec.stable == {"hair_color": "red"}
    assert spec.current == {}


def test_set_visual_asset_reference_rejects_an_unknown_asset_kind(db_session):
    campaign = create_campaign(db_session, "Visual Assets Tipo Invalido", world_seed=106)

    with pytest.raises(FutureAssetKindError):
        set_visual_asset_reference(
            db_session, "npc", "npc_mira", "NPC_SELFIE", "asset_x",
            campaign_id=campaign.id,
        )


def test_future_asset_kinds_matches_the_exact_set_named_in_the_spec():
    assert set(FUTURE_ASSET_KINDS) == {
        "NPC_PORTRAIT",
        "NPC_FULL_BODY",
        "ITEM_ILLUSTRATION",
        "CREATURE_ILLUSTRATION",
        "LOCATION_SCENE",
        "SETTLEMENT_SCENE",
        "REGION_ART",
        "ORGANIZATION_EMBLEM",
        "MAP_ASSET",
    }
