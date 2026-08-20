import json

import pytest

from app.core.enums import ClassOfferStatus, EventType
from app.db.models.character_class import CharacterClassOffer, ClassDefinition
from app.db.models.event import WorldEvent
from app.db.models.profession import CharacterProfession
from app.game.character.service import create_character
from app.game.classes.service import (
    ClassChoiceError,
    accept_class_offer,
    create_class_definition,
    create_class_offer,
    delay_class_offer,
    get_active_class,
    list_visible_class_offers,
    make_class_offer_available,
)
from app.game.world.reset import delete_campaign
from app.game.professions.service import award_profession_xp
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session, name="Hero"):
    campaign = create_campaign(db_session, f"Class Test {name}")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        name,
        region.id,
        location.id,
    )
    return campaign, character


def _offer(db_session, campaign, character, name="Espadachim do Vento"):
    class_definition = create_class_definition(
        db_session,
        campaign.id,
        name,
        "Um caminho reconhecido pelo System sem conceder capacidades novas.",
    )
    return class_definition, create_class_offer(
        db_session,
        campaign.id,
        character,
        class_definition,
    )


def test_new_level_zero_character_has_no_class_or_offers(db_session):
    _campaign, character = _character(db_session)

    assert character.level == 0
    assert character.active_class_id is None
    assert get_active_class(db_session, character) is None
    assert list_visible_class_offers(db_session, character.id) == []
    assert db_session.query(CharacterClassOffer).count() == 0


def test_pending_offer_is_hidden_until_safe_notification(db_session):
    campaign, character = _character(db_session)
    _class_definition, offer = _offer(db_session, campaign, character)

    assert offer.status == ClassOfferStatus.PENDING.value
    assert list_visible_class_offers(db_session, character.id) == []

    make_class_offer_available(
        db_session,
        campaign.id,
        character,
        offer,
        safe_to_notify=False,
    )
    assert offer.status == ClassOfferStatus.PENDING.value

    make_class_offer_available(
        db_session,
        campaign.id,
        character,
        offer,
        safe_to_notify=True,
    )
    assert offer.status == ClassOfferStatus.AVAILABLE.value
    assert list_visible_class_offers(db_session, character.id) == [offer]


def test_multiple_class_offers_can_be_available(db_session):
    campaign, character = _character(db_session)
    _first_class, first = _offer(db_session, campaign, character, "Lâmina Flamejante")
    _second_class, second = _offer(db_session, campaign, character, "Cavaleiro das Chamas")
    for offer in (first, second):
        make_class_offer_available(
            db_session,
            campaign.id,
            character,
            offer,
            safe_to_notify=True,
        )

    assert list_visible_class_offers(db_session, character.id) == [first, second]


def test_delaying_keeps_offer_available_for_later_acceptance(db_session):
    campaign, character = _character(db_session)
    class_definition, offer = _offer(db_session, campaign, character)
    make_class_offer_available(
        db_session,
        campaign.id,
        character,
        offer,
        safe_to_notify=True,
    )

    delayed = delay_class_offer(db_session, campaign.id, character, offer)

    assert delayed.status == ClassOfferStatus.DELAYED.value
    assert list_visible_class_offers(db_session, character.id) == [offer]
    assert character.active_class_id is None

    accepted = accept_class_offer(db_session, campaign.id, character, offer)
    assert accepted is class_definition
    assert character.active_class_id == class_definition.id
    assert offer.status == ClassOfferStatus.ACCEPTED.value
    assert list_visible_class_offers(db_session, character.id) == []


def test_level_zero_can_accept_class_without_receiving_powers(db_session):
    campaign, character = _character(db_session)
    _class_definition, offer = _offer(db_session, campaign, character, "Curandeiro")
    make_class_offer_available(
        db_session,
        campaign.id,
        character,
        offer,
        safe_to_notify=True,
    )
    before = (
        character.level,
        character.xp,
        character.hp_max,
        character.mana_max,
        character.stamina_max,
    )

    accept_class_offer(db_session, campaign.id, character, offer)

    assert character.level == 0
    assert (
        character.level,
        character.xp,
        character.hp_max,
        character.mana_max,
        character.stamina_max,
    ) == before
    event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.PLAYER_CLASS_ACCEPTED.value)
        .one()
    )
    assert json.loads(event.payload_json)["class_name"] == "Curandeiro"


def test_character_cannot_activate_second_class(db_session):
    campaign, character = _character(db_session)
    _first_class, first = _offer(db_session, campaign, character, "Mago Restaurador")
    _second_class, second = _offer(db_session, campaign, character, "Guardião da Vida")
    for offer in (first, second):
        make_class_offer_available(
            db_session,
            campaign.id,
            character,
            offer,
            safe_to_notify=True,
        )
    accept_class_offer(db_session, campaign.id, character, first)

    with pytest.raises(ClassChoiceError, match="already has an active class"):
        accept_class_offer(db_session, campaign.id, character, second)

    assert second.status == ClassOfferStatus.AVAILABLE.value


def test_offer_cannot_cross_campaign_or_character_boundary(db_session):
    campaign, character = _character(db_session, "First")
    other_campaign, other_character = _character(db_session, "Second")
    class_definition, offer = _offer(db_session, campaign, character)

    with pytest.raises(ValueError, match="does not belong to character"):
        make_class_offer_available(
            db_session,
            other_campaign.id,
            other_character,
            offer,
            safe_to_notify=True,
        )

    with pytest.raises(ValueError, match="does not belong to campaign"):
        create_class_offer(
            db_session,
            other_campaign.id,
            other_character,
            class_definition,
        )


def test_campaign_reset_removes_class_state(db_session):
    campaign, character = _character(db_session)
    _class_definition, _offer_row = _offer(db_session, campaign, character)
    award_profession_xp(
        db_session,
        campaign.id,
        character,
        profession_key="HERBALISM",
        profession_name="Herbalismo",
        amount=0.1,
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(CharacterClassOffer).count() == 0
    assert db_session.query(ClassDefinition).count() == 0
    assert db_session.query(CharacterProfession).count() == 0


def test_class_offer_api_hides_pending_and_supports_delay_then_accept(
    client,
    db_session,
):
    campaign, character = _character(db_session)
    class_definition, offer = _offer(db_session, campaign, character)
    db_session.commit()

    sheet_url = f"/api/campaigns/{campaign.id}/character"
    pending_sheet = client.get(
        sheet_url,
        params={"character_id": character.id},
    ).json()
    assert pending_sheet["active_class"] is None
    assert pending_sheet["class_offers"] == []

    make_class_offer_available(
        db_session,
        campaign.id,
        character,
        offer,
        safe_to_notify=True,
    )
    db_session.commit()
    available_sheet = client.get(
        sheet_url,
        params={"character_id": character.id},
    ).json()
    assert available_sheet["class_offers"][0]["status"] == "AVAILABLE"

    choice_url = (
        f"/api/campaigns/{campaign.id}/character/"
        f"class-offers/{offer.id}"
    )
    delayed = client.post(
        f"{choice_url}/delay",
        params={"character_id": character.id},
    )
    assert delayed.status_code == 200
    assert delayed.json()["status"] == "DELAYED"

    accepted = client.post(
        f"{choice_url}/accept",
        params={"character_id": character.id},
    )
    assert accepted.status_code == 200
    assert accepted.json()["id"] == class_definition.id

    active_sheet = client.get(
        sheet_url,
        params={"character_id": character.id},
    ).json()
    assert active_sheet["active_class"]["name"] == "Espadachim do Vento"
    assert active_sheet["class_offers"] == []
