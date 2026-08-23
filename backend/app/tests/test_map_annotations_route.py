"""Phase 20J — Player Map Annotations (API routes)."""

from app.core.enums import DiscoveryStatus
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.world.seed import create_campaign, seed_initial_region


def test_post_annotation_creates_and_returns_it(client, db_session):
    campaign = create_campaign(db_session, "Rota Criar Anotacao", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign.id}/map-annotations",
        json={"character_id": character.id, "location_id": village.id, "text": "Bom poço aqui."},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["location_id"] == village.id
    assert body["text"] == "Bom poço aqui."


def test_post_annotation_for_unknown_location_returns_400(client, db_session):
    campaign = create_campaign(db_session, "Rota Anotacao Local Desconhecido", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.commit()

    response = client.post(
        f"/api/campaigns/{campaign.id}/map-annotations",
        json={"character_id": character.id, "location_id": "loc_inexistente", "text": "Nota."},
    )

    assert response.status_code == 400


def test_delete_annotation_by_owner_succeeds(client, db_session):
    campaign = create_campaign(db_session, "Rota Apagar Anotacao", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    db_session.commit()

    created = client.post(
        f"/api/campaigns/{campaign.id}/map-annotations",
        json={"character_id": character.id, "location_id": village.id, "text": "Nota."},
    ).json()

    response = client.delete(
        f"/api/campaigns/{campaign.id}/map-annotations/{created['id']}",
        params={"character_id": character.id},
    )

    assert response.status_code == 200
    assert response.json()["deleted"] is True


def test_delete_annotation_by_a_different_character_returns_404(client, db_session):
    campaign = create_campaign(db_session, "Rota Apagar Anotacao Alheia", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    mira = create_character(db_session, campaign.id, "Mira", region.id, village.id)
    set_location_discovery(db_session, logan.id, village.id, DiscoveryStatus.VISITED)
    db_session.commit()

    created = client.post(
        f"/api/campaigns/{campaign.id}/map-annotations",
        json={"character_id": logan.id, "location_id": village.id, "text": "Nota do Logan."},
    ).json()

    response = client.delete(
        f"/api/campaigns/{campaign.id}/map-annotations/{created['id']}",
        params={"character_id": mira.id},
    )

    assert response.status_code == 404
