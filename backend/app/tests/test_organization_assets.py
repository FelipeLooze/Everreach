"""Phase 13J — Organization Resources & Assets.

Guildmaster owns sword != Guild owns sword: an item's physical existence
stays entirely governed by the real Phase 10 Item system (add_item, the
same function characters use) — OrganizationAsset only adds who the
beneficial organizational owner is, as a thin overlay, since
ItemInstance.owner_type is hard-constrained to CHARACTER/NPC/NONE at the
database level and was not touched.
"""

import pytest

from app.core.enums import OrganizationOrigin, OrganizationType
from app.game.character.service import create_character
from app.game.inventory.service import add_item
from app.game.organizations.assets import (
    assign_item_to_organization,
    deposit_funds,
    organization_assets,
    unassign_item_from_organization,
    withdraw_funds,
)
from app.game.organizations.service import OrganizationError, create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Organization Assets")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    org = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    db_session.flush()
    return campaign, region, village, character, org


def test_assigning_an_item_does_not_touch_its_physical_ownership(db_session):
    campaign, region, village, character, org = _setup(db_session)
    bow = add_item(db_session, character.id, "Arco Longo")

    assign_item_to_organization(db_session, org, bow)

    assert bow.owner_type == "CHARACTER"
    assert bow.owner_ref == character.id
    assert bow in organization_assets(db_session, org.id)


def test_reassigning_the_same_item_is_idempotent(db_session):
    campaign, region, village, character, org = _setup(db_session)
    bow = add_item(db_session, character.id, "Arco Longo")

    first = assign_item_to_organization(db_session, org, bow)
    second = assign_item_to_organization(db_session, org, bow)

    assert first.id == second.id


def test_an_item_cannot_belong_to_two_organizations(db_session):
    campaign, region, village, character, org = _setup(db_session)
    other_org = create_organization(
        db_session, campaign.id, "Templo de Cardal",
        organization_type=OrganizationType.RELIGIOUS, origin=OrganizationOrigin.NATIVE,
    )
    bow = add_item(db_session, character.id, "Arco Longo")
    assign_item_to_organization(db_session, org, bow)

    with pytest.raises(OrganizationError):
        assign_item_to_organization(db_session, other_org, bow)


def test_unassigning_removes_it_from_the_organizations_assets(db_session):
    campaign, region, village, character, org = _setup(db_session)
    bow = add_item(db_session, character.id, "Arco Longo")
    asset = assign_item_to_organization(db_session, org, bow)

    unassign_item_from_organization(db_session, asset)

    assert organization_assets(db_session, org.id) == []


def test_treasury_starts_at_zero(db_session):
    campaign, region, village, character, org = _setup(db_session)

    assert org.treasury == 0.0


def test_deposit_and_withdraw_funds(db_session):
    campaign, region, village, character, org = _setup(db_session)

    deposit_funds(db_session, org, 50.0, reason="Doação de um membro.")
    withdraw_funds(db_session, org, 20.0, reason="Compra de flechas.")

    assert org.treasury == 30.0


def test_cannot_withdraw_more_than_the_treasury_holds(db_session):
    campaign, region, village, character, org = _setup(db_session)
    deposit_funds(db_session, org, 10.0, reason="Doação.")

    with pytest.raises(OrganizationError):
        withdraw_funds(db_session, org, 50.0, reason="Compra cara demais.")


def test_funds_change_requires_a_reason(db_session):
    campaign, region, village, character, org = _setup(db_session)

    with pytest.raises(OrganizationError):
        deposit_funds(db_session, org, 10.0, reason="  ")
