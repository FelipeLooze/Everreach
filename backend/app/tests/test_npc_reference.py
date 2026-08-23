"""Phase 23D-H — NPC Canonical Reference Support."""
import pytest

from app.db.models.visual_asset import VisualAsset
from app.game.visual.npc_reference import (
    NPCReferenceError,
    get_canonical_reference,
    get_current_portrait,
    set_canonical_reference,
)
from app.game.world.seed import create_campaign


def _asset(campaign_id, **overrides) -> VisualAsset:
    params = dict(
        campaign_id=campaign_id,
        entity_type="npc",
        entity_id="npc_mira",
        asset_type="NPC_PORTRAIT",
        storage_path="npcs/npc_mira/NPC_PORTRAIT/vasset_x.png",
        mime_type="image/png",
        width=1024,
        height=1024,
        workflow_key="EVERREACH_NPC_PORTRAIT",
        workflow_version="V1",
        model_identifier="flux-2-klein-4b",
        seed=5001,
    )
    params.update(overrides)
    return VisualAsset(**params)


def test_get_canonical_reference_is_none_until_established(db_session):
    campaign = create_campaign(db_session, "NPC Ref Ausente", world_seed=401)

    assert get_canonical_reference(db_session, campaign.id, "npc_mira") is None


def test_set_canonical_reference_designates_the_asset(db_session):
    campaign = create_campaign(db_session, "NPC Ref Definido", world_seed=402)
    asset = _asset(campaign.id)
    db_session.add(asset)
    db_session.commit()

    reference = set_canonical_reference(db_session, campaign.id, "npc_mira", asset.id)

    assert reference.is_canonical_reference is True
    assert get_canonical_reference(db_session, campaign.id, "npc_mira").id == asset.id


def test_set_canonical_reference_demotes_the_previous_one(db_session):
    campaign = create_campaign(db_session, "NPC Ref Substituido", world_seed=403)
    v1 = _asset(campaign.id)
    v2 = _asset(campaign.id)
    db_session.add_all([v1, v2])
    db_session.commit()
    set_canonical_reference(db_session, campaign.id, "npc_mira", v1.id)

    set_canonical_reference(db_session, campaign.id, "npc_mira", v2.id)

    db_session.refresh(v1)
    db_session.refresh(v2)
    assert v1.is_canonical_reference is False
    assert v2.is_canonical_reference is True


def test_set_canonical_reference_raises_for_unknown_asset(db_session):
    campaign = create_campaign(db_session, "NPC Ref Inexistente", world_seed=404)

    with pytest.raises(NPCReferenceError):
        set_canonical_reference(db_session, campaign.id, "npc_mira", "vasset_does_not_exist")


def test_set_canonical_reference_rejects_an_asset_belonging_to_a_different_npc(db_session):
    campaign = create_campaign(db_session, "NPC Ref NPC Errado", world_seed=405)
    asset = _asset(campaign.id, entity_id="npc_logan")
    db_session.add(asset)
    db_session.commit()

    with pytest.raises(NPCReferenceError):
        set_canonical_reference(db_session, campaign.id, "npc_mira", asset.id)


def test_set_canonical_reference_rejects_an_asset_from_another_campaign(db_session):
    campaign_a = create_campaign(db_session, "NPC Ref Campanha A", world_seed=406)
    campaign_b = create_campaign(db_session, "NPC Ref Campanha B", world_seed=407)
    asset = _asset(campaign_a.id)
    db_session.add(asset)
    db_session.commit()

    with pytest.raises(NPCReferenceError):
        set_canonical_reference(db_session, campaign_b.id, "npc_mira", asset.id)


def test_get_current_portrait_returns_the_most_recent_npc_portrait(db_session):
    campaign = create_campaign(db_session, "NPC Portrait Atual", world_seed=408)
    older = _asset(campaign.id, seed=1)
    db_session.add(older)
    db_session.commit()
    newer = _asset(campaign.id, seed=2)
    db_session.add(newer)
    db_session.commit()

    current = get_current_portrait(db_session, campaign.id, "npc_mira")

    assert current.id == newer.id


def test_get_current_portrait_ignores_other_asset_types(db_session):
    campaign = create_campaign(db_session, "NPC Portrait Outro Tipo", world_seed=409)
    full_body = _asset(campaign.id, asset_type="NPC_FULL_BODY")
    db_session.add(full_body)
    db_session.commit()

    assert get_current_portrait(db_session, campaign.id, "npc_mira") is None
