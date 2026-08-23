"""Phase 21O — Visual Presentation Contracts (NPC / Location / Organization)."""

import pytest

from app.core.enums import DiscoveryStatus, OrganizationOrigin, OrganizationType
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.organizations.service import create_organization
from app.game.visual.npc import set_npc_stable_identity
from app.game.visual.organization import set_organization_heraldry
from app.game.visual.presentation import (
    VisualPresentationError,
    build_location_presentation,
    build_npc_presentation,
    build_organization_presentation,
)
from app.game.world.seed import create_campaign, seed_initial_region


def test_npc_presentation_carries_resolved_visual_traits(db_session):
    campaign = create_campaign(db_session, "Apresentacao NPC", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(campaign_id=campaign.id, region_id=region.id, location_id=village.id, name="Mira", role="ferreira")
    db_session.add(npc)
    db_session.flush()
    set_npc_stable_identity(db_session, campaign.id, npc.id, {"hair_color": "red"})

    presentation = build_npc_presentation(db_session, campaign.id, npc.id)

    assert presentation.display_name == "Mira"
    assert presentation.visual_traits["hair_color"] == "red"
    assert presentation.has_visual_detail is True


def test_npc_presentation_has_no_visual_detail_when_nothing_was_ever_established(db_session):
    campaign = create_campaign(db_session, "Apresentacao NPC Sem Detalhe", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(campaign_id=campaign.id, region_id=region.id, location_id=village.id, name="Guarda", role="guarda")
    db_session.add(npc)
    db_session.flush()

    presentation = build_npc_presentation(db_session, campaign.id, npc.id)

    assert presentation.has_visual_detail is False


def test_npc_presentation_raises_for_a_nonexistent_npc(db_session):
    campaign = create_campaign(db_session, "Apresentacao NPC Inexistente", world_seed=3)

    with pytest.raises(VisualPresentationError):
        build_npc_presentation(db_session, campaign.id, "npc_nao_existe")


def test_location_presentation_is_none_for_a_location_outside_the_characters_map_view(db_session):
    from app.db.models.location import Location

    campaign = create_campaign(db_session, "Apresentacao Local Fora Do Mapa", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    hidden = Location(region_id=region.id, name="Nunca Visto", type="generic")
    db_session.add(hidden)
    db_session.flush()

    presentation = build_location_presentation(db_session, campaign.id, character.id, hidden.id)

    assert presentation is None


def test_location_presentation_reflects_the_characters_own_map_view(db_session):
    campaign = create_campaign(db_session, "Apresentacao Local Visivel", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    presentation = build_location_presentation(db_session, campaign.id, character.id, village.id)

    assert presentation is not None
    assert presentation.location_id == village.id


def test_organization_presentation_merges_stable_and_current_heraldry(db_session):
    campaign = create_campaign(db_session, "Apresentacao Organizacao", world_seed=6)
    org = create_organization(
        db_session, campaign.id, "Guilda dos Mercadores",
        organization_type=OrganizationType.COMMERCIAL, origin=OrganizationOrigin.NATIVE,
    )
    set_organization_heraldry(db_session, campaign.id, org.id, {"emblem_description": "silver scale"})

    presentation = build_organization_presentation(db_session, campaign.id, org.id)

    assert presentation.display_name == "Guilda dos Mercadores"
    assert presentation.visual_traits["emblem_description"] == "silver scale"
    assert presentation.has_visual_detail is True


def test_organization_presentation_raises_for_a_nonexistent_organization(db_session):
    campaign = create_campaign(db_session, "Apresentacao Organizacao Inexistente", world_seed=7)

    with pytest.raises(VisualPresentationError):
        build_organization_presentation(db_session, campaign.id, "org_nao_existe")
