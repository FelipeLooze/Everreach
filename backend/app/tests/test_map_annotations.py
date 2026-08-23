"""Phase 20J — Player Map Annotations (service layer)."""

import pytest

from app.core.enums import DiscoveryStatus
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.map.annotations import AnnotationError, create_annotation, delete_annotation, list_annotations
from app.game.world.seed import create_campaign, seed_initial_region


def test_can_annotate_a_visible_location(db_session):
    campaign = create_campaign(db_session, "Anotar Local Visivel", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    annotation = create_annotation(db_session, campaign.id, character.id, village.id, "Bom ferreiro aqui.")

    assert annotation.location_id == village.id
    assert annotation.text == "Bom ferreiro aqui."


def test_cannot_annotate_a_location_the_character_does_not_know(db_session):
    from app.db.models.location import Location

    campaign = create_campaign(db_session, "Nao Pode Anotar Desconhecido", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    hidden = Location(region_id=region.id, name="Nunca Visto", type="generic")
    db_session.add(hidden)
    db_session.flush()

    with pytest.raises(AnnotationError):
        create_annotation(db_session, campaign.id, character.id, hidden.id, "Suposto covil de dragao.")


def test_cannot_create_an_empty_annotation(db_session):
    campaign = create_campaign(db_session, "Anotacao Vazia", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    with pytest.raises(AnnotationError):
        create_annotation(db_session, campaign.id, character.id, village.id, "   ")


def test_annotation_never_mutates_world_truth(db_session):
    """The mandatory spec rule: writing 'Dragon nest.' never creates a
    dragon nest — the Location row itself must stay untouched."""
    campaign = create_campaign(db_session, "Anotacao Nunca Vira Verdade", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    original_description = village.description

    create_annotation(db_session, campaign.id, character.id, village.id, "Ninho de dragao aqui.")

    db_session.refresh(village)
    assert village.description == original_description
    assert "dragao" not in village.name.lower()


def test_only_the_owning_character_can_delete_their_annotation(db_session):
    campaign = create_campaign(db_session, "Apenas Dono Pode Apagar", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    mira = create_character(db_session, campaign.id, "Mira", region.id, village.id)
    set_location_discovery(db_session, logan.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, mira.id, village.id, DiscoveryStatus.VISITED)
    annotation = create_annotation(db_session, campaign.id, logan.id, village.id, "Nota do Logan.")

    assert delete_annotation(db_session, mira.id, annotation.id) is False
    assert delete_annotation(db_session, logan.id, annotation.id) is True
    assert list_annotations(db_session, campaign.id, logan.id) == []


def test_list_annotations_is_scoped_to_campaign_and_character(db_session):
    campaign_a = create_campaign(db_session, "Campanha Anotacao A", world_seed=6)
    campaign_b = create_campaign(db_session, "Campanha Anotacao B", world_seed=7)
    region_a, village_a = seed_initial_region(db_session, campaign_a.id)
    logan = create_character(db_session, campaign_a.id, "Logan", region_a.id, village_a.id)
    set_location_discovery(db_session, logan.id, village_a.id, DiscoveryStatus.VISITED)
    create_annotation(db_session, campaign_a.id, logan.id, village_a.id, "Nota de Logan.")

    assert len(list_annotations(db_session, campaign_a.id, logan.id)) == 1
    assert list_annotations(db_session, campaign_b.id, logan.id) == []
