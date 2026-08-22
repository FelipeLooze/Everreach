"""Phase 17G — Physical Maps."""

import pytest

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, ItemInstanceMode, ItemType, KnowerType
from app.db.models.item import Item, ItemInstance
from app.game.character.service import create_character
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.knowledge.maps import create_map, map_content
from app.game.world.seed import create_campaign


def _grant_mappable_knowledge(db_session, campaign_id, character_id, subject_kind, entity_id):
    for aspect, statement in [
        (GeographicKnowledgeAspect.EXISTENCE, "Uma grande cidade existe ao sul."),
        (GeographicKnowledgeAspect.DIRECTION, "Fica ao sul de Cardal."),
    ]:
        ensure_geographic_fact(db_session, campaign_id, subject_kind, entity_id, aspect, statement)
        grant_geographic_knowledge(
            db_session, campaign_id, KnowerType.PLAYER, character_id, subject_kind, entity_id, aspect,
            precision=GeographicPrecision.APPROXIMATE,
        )


def test_cannot_map_what_is_not_known(db_session):
    campaign = create_campaign(db_session, "Sem Mapa Possivel", world_seed=1)
    logan = create_character(db_session, campaign.id, "Logan")

    with pytest.raises(ValueError):
        create_map(db_session, campaign.id, logan.id, "settlement", "loc_never_taught")


def test_creating_a_map_produces_a_real_unique_item_in_inventory(db_session):
    campaign = create_campaign(db_session, "Mapa Real", world_seed=2)
    logan = create_character(db_session, campaign.id, "Logan")
    _grant_mappable_knowledge(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    instance, map_row = create_map(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    assert instance.owner_type == "CHARACTER"
    assert instance.owner_ref == logan.id
    assert instance.location_type == "CHARACTER"
    assert instance.location_ref == logan.id

    definition = db_session.get(Item, instance.definition_id)
    assert definition.type == ItemType.MAP.value
    assert definition.instance_mode == ItemInstanceMode.UNIQUE.value

    assert map_row.item_instance_id == instance.id
    assert map_row.subject_kind == "settlement"
    assert map_row.entity_id == "loc_arven"
    assert map_row.creator_id == logan.id


def test_map_content_is_a_frozen_snapshot_of_the_survey(db_session):
    campaign = create_campaign(db_session, "Mapa Congelado", world_seed=3)
    logan = create_character(db_session, campaign.id, "Logan")
    _grant_mappable_knowledge(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    _instance, map_row = create_map(db_session, campaign.id, logan.id, "settlement", "loc_arven")
    content = map_content(map_row)

    aspects_by_name = {a["aspect"]: a for a in content["aspects"]}
    assert "EXISTENCE" in aspects_by_name
    assert "DIRECTION" in aspects_by_name
    assert aspects_by_name["DIRECTION"]["precision"] == GeographicPrecision.APPROXIMATE.value

    # Learning MORE afterward must never rewrite an already-created map.
    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.DANGERS,
        "A estrada tem bandidos ocasionais.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "settlement", "loc_arven", GeographicKnowledgeAspect.DANGERS,
    )

    content_after = map_content(map_row)
    assert {a["aspect"] for a in content_after["aspects"]} == {"EXISTENCE", "DIRECTION"}


def test_two_maps_of_the_same_place_are_distinct_items(db_session):
    campaign = create_campaign(db_session, "Dois Mapas", world_seed=4)
    logan = create_character(db_session, campaign.id, "Logan")
    _grant_mappable_knowledge(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    instance_a, _map_a = create_map(db_session, campaign.id, logan.id, "settlement", "loc_arven")
    instance_b, _map_b = create_map(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    assert instance_a.id != instance_b.id
    count = db_session.query(ItemInstance).filter(ItemInstance.definition_id == instance_a.definition_id).count()
    assert count == 2
