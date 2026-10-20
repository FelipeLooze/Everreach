from app.db.models.campaign import Campaign, WorldTime
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.db.models.knowledge_index import IndexedKnowledgeDocument
from app.db.models.npc import NPC
from app.db.models.region import Region
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.memory import Memory
from app.db.models.relationship import CharacterNPCRelationship


def _create_started_campaign(client, campaign_name: str, character_name: str):
    campaign = client.post("/api/campaigns", json={"name": campaign_name}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": character_name}
    ).json()
    response = client.post(
        f"/api/campaigns/{campaign['id']}/start", params={"character_id": character["id"]}
    )
    assert response.status_code == 200
    return campaign, character


def test_reset_deletes_only_the_selected_campaign(client, db_session):
    deleted_campaign, deleted_character = _create_started_campaign(client, "Apagar", "Primeiro")
    kept_campaign, kept_character = _create_started_campaign(client, "Preservar", "Segundo")

    response = client.delete(f"/api/campaigns/{deleted_campaign['id']}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    db_session.expire_all()
    assert db_session.get(Campaign, deleted_campaign["id"]) is None
    assert db_session.get(Character, deleted_character["id"]) is None
    assert db_session.query(Region).filter(Region.campaign_id == deleted_campaign["id"]).count() == 0
    assert db_session.query(WorldTime).filter(WorldTime.campaign_id == deleted_campaign["id"]).count() == 0
    assert db_session.query(WorldEvent).filter(WorldEvent.campaign_id == deleted_campaign["id"]).count() == 0
    assert db_session.query(Memory).filter(Memory.campaign_id == deleted_campaign["id"]).count() == 0
    assert (
        db_session.query(IndexedKnowledgeDocument)
        .filter(IndexedKnowledgeDocument.campaign_id == deleted_campaign["id"])
        .count()
        == 0
    )
    assert (
        db_session.query(CharacterNPCRelationship)
        .filter(CharacterNPCRelationship.campaign_id == deleted_campaign["id"])
        .count()
        == 0
    )
    assert db_session.query(NPC).filter(NPC.campaign_id == deleted_campaign["id"]).count() == 0
    assert (
        db_session.query(SimulatedPlayer)
        .filter(SimulatedPlayer.campaign_id == deleted_campaign["id"])
        .count()
        == 0
    )

    assert db_session.get(Campaign, kept_campaign["id"]) is not None
    assert db_session.get(Character, kept_character["id"]) is not None
    assert client.get(f"/api/campaigns/{kept_campaign['id']}").status_code == 200
    assert client.get(f"/api/campaigns/{deleted_campaign['id']}").status_code == 404


def test_reset_unknown_campaign_returns_404(client):
    response = client.delete("/api/campaigns/campaign_inexistente")
    assert response.status_code == 404


def test_reset_deletes_economic_canon_values(client, db_session):
    from app.db.models.economic_value import EconomicCanonValue
    from app.db.models.location import Location

    campaign, _ = _create_started_campaign(client, "Apagar", "Mercador")
    location = (
        db_session.query(Location)
        .join(Region, Location.region_id == Region.id)
        .filter(Region.campaign_id == campaign["id"])
        .first()
    )
    db_session.add(
        EconomicCanonValue(
            campaign_id=campaign["id"],
            canonical_key=f"service:{location.id}:pernoite",
            subject_type="SERVICE",
            subject_id="pernoite",
            location_id=location.id,
            classification="MARKET_PRICE",
            base_price_bronze=12,
            provenance="DETERMINISTIC",
            created_world_minute=0,
        )
    )
    db_session.commit()

    response = client.delete(f"/api/campaigns/{campaign['id']}")

    assert response.status_code == 200
    db_session.expire_all()
    assert (
        db_session.query(EconomicCanonValue)
        .filter(EconomicCanonValue.campaign_id == campaign["id"])
        .count()
        == 0
    )


def test_reset_deletes_shops_groups_wallets_and_map_annotations(db_session):
    from app.core.enums import CombatActorType, DiscoveryStatus, GroupType, ItemType
    from app.db.models.currency import CurrencyHolding
    from app.db.models.group import Group, GroupMember
    from app.db.models.map_annotation import MapAnnotation
    from app.db.models.shop import Shop, ShopListing
    from app.game.character.service import create_character
    from app.game.discovery.service import set_location_discovery
    from app.game.economy.pricing import set_item_base_value
    from app.game.economy.shops import create_shop, stock_item
    from app.game.economy.wallet import deposit, get_or_create_holding
    from app.game.groups.service import create_group
    from app.game.inventory.service import add_item, get_or_create_item
    from app.game.map.annotations import create_annotation
    from app.game.world.reset import delete_campaign
    from app.game.world.seed import create_campaign, seed_initial_region

    campaign = create_campaign(db_session, "Apagar Tudo")
    region, village = seed_initial_region(db_session, campaign.id)
    hero = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    merchant = create_character(db_session, campaign.id, "Merchant", region.id, village.id)
    shop = create_shop(
        db_session, campaign.id, "Ferraria", CombatActorType.CHARACTER, merchant.id,
        location_id=village.id, accepted_item_types=(ItemType.TOOL,),
    )
    set_item_base_value(db_session, get_or_create_item(db_session, "Machado", "TOOL"), 40)
    stock_item(db_session, shop, add_item(db_session, merchant.id, "Machado"))
    deposit(
        db_session,
        get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, hero.id),
        100,
        reason="Saldo inicial.",
    )
    create_group(
        db_session, campaign.id,
        group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, hero.id), (CombatActorType.CHARACTER, merchant.id)],
    )
    set_location_discovery(db_session, hero.id, village.id, DiscoveryStatus.VISITED)
    create_annotation(db_session, campaign.id, hero.id, village.id, "Bom poço aqui.")
    db_session.commit()

    assert delete_campaign(db_session, campaign.id) is True
    db_session.commit()

    assert db_session.query(Shop).count() == 0
    assert db_session.query(ShopListing).count() == 0
    assert db_session.query(CurrencyHolding).filter(CurrencyHolding.campaign_id == campaign.id).count() == 0
    assert db_session.query(Group).count() == 0
    assert db_session.query(GroupMember).count() == 0
    assert db_session.query(MapAnnotation).count() == 0


def test_reset_covers_every_campaign_scoped_table():
    """Guard: any table that can reach `campaigns` through a FK chain must be
    torn down by delete_campaign, or deleting a save fails with an FK error
    once that table gets its first row."""
    import inspect
    import re

    import app.db.models  # noqa: F401 — registers every mapper
    from app.db.base import Base
    from app.game.world import reset

    source = inspect.getsource(reset)
    classes = {mapper.local_table.name: mapper.class_ for mapper in Base.registry.mappers}
    scoped = {"campaigns"}
    changed = True
    while changed:
        changed = False
        for table in Base.metadata.tables.values():
            if table.name not in scoped and any(
                fk.column.table.name in scoped for fk in table.foreign_keys
            ):
                scoped.add(table.name)
                changed = True

    missing = sorted(
        table for table in scoped
        if not re.search(rf"\b{classes[table].__name__}\b", source)
    )
    assert missing == []
