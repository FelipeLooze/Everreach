"""Phase 20J — Player Map Annotations (Map View integration)."""

from app.core.enums import DiscoveryStatus
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.map.annotations import create_annotation
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def test_annotation_appears_in_the_map_view(db_session):
    campaign = create_campaign(db_session, "Anotacao No Map View", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    create_annotation(db_session, campaign.id, character.id, village.id, "Bom lugar para descansar.")

    view = get_map_view(db_session, campaign.id, character.id)

    assert len(view.annotations) == 1
    assert view.annotations[0].location_id == village.id
    assert view.annotations[0].text == "Bom lugar para descansar."


def test_annotations_are_isolated_per_character(db_session):
    campaign = create_campaign(db_session, "Anotacao Isolada Por Personagem", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    mira = create_character(db_session, campaign.id, "Mira", region.id, village.id)
    set_location_discovery(db_session, logan.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, mira.id, village.id, DiscoveryStatus.VISITED)
    create_annotation(db_session, campaign.id, logan.id, village.id, "Nota do Logan.")

    logan_view = get_map_view(db_session, campaign.id, logan.id)
    mira_view = get_map_view(db_session, campaign.id, mira.id)

    assert len(logan_view.annotations) == 1
    assert mira_view.annotations == []


def test_annotation_disappears_when_scope_excludes_its_location(db_session):
    campaign = create_campaign(db_session, "Anotacao Some Fora De Escopo", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    create_annotation(db_session, campaign.id, character.id, village.id, "Nota qualquer.")

    view = get_map_view(db_session, campaign.id, character.id, scope="world")

    assert view.annotations == []


def test_annotation_reappears_when_scope_includes_its_location_again(db_session):
    campaign = create_campaign(db_session, "Anotacao Volta Com Escopo Certo", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    create_annotation(db_session, campaign.id, character.id, village.id, "Nota qualquer.")

    view = get_map_view(db_session, campaign.id, character.id, scope=f"region:{region.id}")

    assert len(view.annotations) == 1
