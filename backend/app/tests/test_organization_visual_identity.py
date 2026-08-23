"""Phase 21J — Organization Heraldry & Symbol Identity."""

import pytest

from app.core.enums import (
    OrganizationFormality,
    OrganizationOrigin,
    OrganizationType,
    OrganizationVisibility,
)
from app.game.organizations.service import create_organization
from app.game.visual.organization import (
    OrganizationVisualIdentityError,
    get_organization_visual_spec,
    set_organization_current_display,
    set_organization_heraldry,
    suggest_heraldry_formality,
)
from app.game.world.seed import create_campaign


def _organization(db_session, campaign_id, name="Guilda dos Mercadores", **kwargs):
    return create_organization(
        db_session, campaign_id, name,
        organization_type=kwargs.pop("organization_type", OrganizationType.COMMERCIAL),
        origin=OrganizationOrigin.NATIVE,
        **kwargs,
    )


def test_heraldry_merges_and_never_silently_replaces_established_canon(db_session):
    campaign = create_campaign(db_session, "Heraldica Mescla", world_seed=1)
    org = _organization(db_session, campaign.id)

    set_organization_heraldry(
        db_session, campaign.id, org.id, {"emblem_description": "silver scale over dark green field"},
    )
    spec = set_organization_heraldry(db_session, campaign.id, org.id, {"official_colors": "green and silver"})

    assert spec.stable == {
        "emblem_description": "silver scale over dark green field",
        "official_colors": "green and silver",
    }


def test_current_display_is_separate_from_the_permanent_heraldry(db_session):
    campaign = create_campaign(db_session, "Heraldica Exibicao Atual", world_seed=2)
    org = _organization(db_session, campaign.id)
    set_organization_heraldry(db_session, campaign.id, org.id, {"emblem_description": "silver scale"})

    spec = set_organization_current_display(db_session, campaign.id, org.id, {"banner_state": "at half-mast"})

    assert spec.current == {"banner_state": "at half-mast"}
    assert spec.stable == {"emblem_description": "silver scale"}


def test_heraldry_is_isolated_per_organization(db_session):
    campaign = create_campaign(db_session, "Heraldica Isolada", world_seed=3)
    guild = _organization(db_session, campaign.id, name="Guilda dos Mercadores")
    other = _organization(db_session, campaign.id, name="Ordem dos Artesãos", organization_type=OrganizationType.ARTISAN)
    set_organization_heraldry(db_session, campaign.id, guild.id, {"emblem_description": "silver scale"})

    assert get_organization_visual_spec(db_session, campaign.id, guild.id).stable == {
        "emblem_description": "silver scale",
    }
    assert get_organization_visual_spec(db_session, campaign.id, other.id).stable == {}


def test_suggests_hidden_mark_for_a_private_organization(db_session):
    campaign = create_campaign(db_session, "Heraldica Privada", world_seed=4)
    org = _organization(db_session, campaign.id, visibility=OrganizationVisibility.PRIVATE)

    assert suggest_heraldry_formality(db_session, org.id) == "hidden_mark"


def test_suggests_hidden_mark_for_a_criminal_organization(db_session):
    campaign = create_campaign(db_session, "Heraldica Criminosa", world_seed=5)
    org = _organization(db_session, campaign.id, organization_type=OrganizationType.CRIMINAL)

    assert suggest_heraldry_formality(db_session, org.id) == "hidden_mark"


def test_suggests_trade_mark_for_a_commercial_organization(db_session):
    campaign = create_campaign(db_session, "Heraldica Comercial", world_seed=6)
    org = _organization(db_session, campaign.id, organization_type=OrganizationType.COMMERCIAL)

    assert suggest_heraldry_formality(db_session, org.id) == "trade_mark"


def test_suggests_formal_heraldry_for_a_recognized_political_organization(db_session):
    campaign = create_campaign(db_session, "Heraldica Politica Formal", world_seed=7)
    org = _organization(db_session, campaign.id, organization_type=OrganizationType.POLITICAL)
    org.formality = OrganizationFormality.FORMALLY_RECOGNIZED.value
    db_session.flush()

    assert suggest_heraldry_formality(db_session, org.id) == "formal_heraldry"


def test_suggests_simple_badge_for_an_ordinary_informal_group(db_session):
    campaign = create_campaign(db_session, "Heraldica Simples", world_seed=8)
    org = _organization(db_session, campaign.id, organization_type=OrganizationType.COMMUNITY)

    assert suggest_heraldry_formality(db_session, org.id) == "simple_badge"


def test_raises_for_a_nonexistent_organization(db_session):
    with pytest.raises(OrganizationVisualIdentityError):
        suggest_heraldry_formality(db_session, "org_nao_existe")
