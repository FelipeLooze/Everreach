"""Phase 20B — Interactive Map Foundation: the /map-view API endpoint."""

from app.core.enums import DiscoveryStatus, KnowerType
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.knowledge.geography import ensure_geographic_fact, grant_fact_with_precision, geographic_fact_key
from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision
from app.game.world.seed import create_campaign, seed_initial_region


def _grant_name(db_session, campaign_id, character_id, subject_kind, entity_id, canonical_name):
    ensure_geographic_fact(
        db_session, campaign_id, subject_kind, entity_id,
        GeographicKnowledgeAspect.NAME, f"Chama-se {canonical_name}.",
    )
    grant_fact_with_precision(
        db_session, campaign_id,
        geographic_fact_key(subject_kind, entity_id, GeographicKnowledgeAspect.NAME),
        KnowerType.PLAYER, character_id, precision=GeographicPrecision.PRECISE,
    )


def test_map_view_endpoint_returns_known_locations_and_regions(client, db_session):
    campaign = create_campaign(db_session, "Rota Mapa View", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/map-view",
        params={"character_id": character.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["campaign_id"] == campaign.id
    assert body["character_id"] == character.id
    assert any(loc["id"] == village.id for loc in body["locations"])
    assert any(reg["id"] == region.id for reg in body["regions"])


def test_map_view_endpoint_omits_unknown_region_name(client, db_session):
    campaign = create_campaign(db_session, "Rota Mapa Regiao Oculta", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/map-view",
        params={"character_id": character.id},
    )

    body = response.json()
    region_row = next(reg for reg in body["regions"] if reg["id"] == region.id)
    assert region_row["name"] is None


def test_map_view_endpoint_reveals_region_name_once_known(client, db_session):
    campaign = create_campaign(db_session, "Rota Mapa Regiao Conhecida", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    _grant_name(db_session, campaign.id, character.id, "region", region.id, region.name)
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/map-view",
        params={"character_id": character.id},
    )

    body = response.json()
    region_row = next(reg for reg in body["regions"] if reg["id"] == region.id)
    assert region_row["name"] == region.name


def test_map_view_endpoint_404s_for_unknown_character(client, db_session):
    campaign = create_campaign(db_session, "Rota Mapa Personagem Invalido", world_seed=4)
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/map-view",
        params={"character_id": "char_nao_existe"},
    )

    assert response.status_code == 404


def test_map_view_endpoint_404s_for_unknown_campaign(client, db_session):
    response = client.get(
        "/api/campaigns/campaign_nao_existe/map-view",
        params={"character_id": "char_nao_existe"},
    )

    assert response.status_code == 404


def test_map_view_endpoint_applies_viewport_bounds(client, db_session):
    from app.db.models.location import Location

    campaign = create_campaign(db_session, "Rota Mapa Viewport", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    far_away = Location(region_id=region.id, name="Bem Longe", type="settlement", x=9999, y=9999)
    db_session.add(far_away)
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, far_away.id, DiscoveryStatus.VISITED)
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/map-view",
        params={
            "character_id": character.id,
            "min_x": -10, "min_y": -10, "max_x": 10, "max_y": 10,
        },
    )

    body = response.json()
    location_ids = {loc["id"] for loc in body["locations"]}
    assert village.id in location_ids
    assert far_away.id not in location_ids
