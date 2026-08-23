"""Phase 23D-L — Asset Versioning."""
from app.db.models.visual_asset import VisualAsset
from app.game.visual.versioning import (
    get_current_asset,
    list_asset_history,
    supersede_current_assets,
)
from app.game.world.seed import create_campaign


def _asset(campaign_id, **overrides) -> VisualAsset:
    params = dict(
        campaign_id=campaign_id, entity_type="npc", entity_id="npc_mira", asset_type="NPC_PORTRAIT",
        storage_path="npcs/npc_mira/NPC_PORTRAIT/vasset_x.png", mime_type="image/png",
        width=1024, height=1024, workflow_key="EVERREACH_NPC_PORTRAIT", workflow_version="V1",
        model_identifier="flux-2-klein-4b", seed=1,
    )
    params.update(overrides)
    return VisualAsset(**params)


def test_get_current_asset_is_none_when_nothing_exists(db_session):
    campaign = create_campaign(db_session, "Versioning None", world_seed=801)

    assert get_current_asset(db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT") is None


def test_supersede_current_assets_demotes_every_other_current_row(db_session):
    campaign = create_campaign(db_session, "Versioning Supersede", world_seed=802)
    old_a = _asset(campaign.id)
    old_b = _asset(campaign.id)
    new = _asset(campaign.id)
    db_session.add_all([old_a, old_b, new])
    db_session.commit()

    superseded = supersede_current_assets(
        db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT", keep_current_id=new.id
    )

    assert {row.id for row in superseded} == {old_a.id, old_b.id}
    db_session.refresh(old_a)
    db_session.refresh(old_b)
    db_session.refresh(new)
    assert old_a.is_current is False
    assert old_b.is_current is False
    assert new.is_current is True


def test_supersede_current_assets_does_not_touch_other_entities_or_asset_types(db_session):
    campaign = create_campaign(db_session, "Versioning Scoped", world_seed=803)
    other_entity = _asset(campaign.id, entity_id="npc_logan")
    other_asset_type = _asset(campaign.id, asset_type="NPC_FULL_BODY")
    new = _asset(campaign.id)
    db_session.add_all([other_entity, other_asset_type, new])
    db_session.commit()

    supersede_current_assets(
        db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT", keep_current_id=new.id
    )

    db_session.refresh(other_entity)
    db_session.refresh(other_asset_type)
    assert other_entity.is_current is True
    assert other_asset_type.is_current is True


def test_get_current_asset_returns_the_only_current_row_after_supersession(db_session):
    campaign = create_campaign(db_session, "Versioning Get Current", world_seed=804)
    old = _asset(campaign.id)
    new = _asset(campaign.id)
    db_session.add_all([old, new])
    db_session.commit()
    supersede_current_assets(
        db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT", keep_current_id=new.id
    )

    current = get_current_asset(db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT")

    assert current.id == new.id


def test_list_asset_history_returns_current_and_superseded_newest_first(db_session):
    campaign = create_campaign(db_session, "Versioning History", world_seed=805)
    old = _asset(campaign.id)
    db_session.add(old)
    db_session.commit()
    new = _asset(campaign.id)
    db_session.add(new)
    db_session.commit()
    supersede_current_assets(
        db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT", keep_current_id=new.id
    )

    history = list_asset_history(db_session, campaign.id, "npc", "npc_mira", "NPC_PORTRAIT")

    assert [row.id for row in history] == [new.id, old.id]
