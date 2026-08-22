"""Phase 20G — Physical Map Integration."""

from app.core.enums import DiscoveryStatus, GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.knowledge.geography import ensure_geographic_fact, geographic_fact_key, grant_fact_with_precision
from app.game.knowledge.maps import create_map
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def _grant(db_session, campaign_id, character_id, location_id, aspect, statement, precision):
    ensure_geographic_fact(db_session, campaign_id, "location", location_id, aspect, statement)
    grant_fact_with_precision(
        db_session, campaign_id,
        geographic_fact_key("location", location_id, aspect),
        KnowerType.PLAYER, character_id, precision=precision,
    )


def _create_and_transfer_map(db_session, campaign_id, creator_id, recipient_id, location_id):
    """Simulates the creator selling/gifting a physical map to another
    character — the map row's own creator_id stays the original
    cartographer, but ownership of the underlying Item moves, exactly
    like any other tradeable Item."""
    instance, map_row = create_map(db_session, campaign_id, creator_id, "location", location_id)
    instance.owner_ref = recipient_id
    db_session.flush()
    return instance, map_row


def test_location_known_only_through_an_owned_map_still_appears(db_session):
    campaign = create_campaign(db_session, "Mapa Fisico Sem Conhecimento Vivo", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    cartographer = create_character(db_session, campaign.id, "Mira", region.id, village.id)
    logan = create_character(db_session, campaign.id, "Logan", region.id, village.id)

    distant = Location(region_id=region.id, name="Arven", type="settlement", x=10, y=20)
    db_session.add(distant)
    db_session.flush()
    _grant(
        db_session, campaign.id, cartographer.id, distant.id,
        GeographicKnowledgeAspect.EXISTENCE, "Um povoado existe ao sul.", GeographicPrecision.VAGUE,
    )
    _grant(
        db_session, campaign.id, cartographer.id, distant.id,
        GeographicKnowledgeAspect.DISTANCE, "Fica a alguns dias.", GeographicPrecision.PRECISE,
    )
    _create_and_transfer_map(db_session, campaign.id, cartographer.id, logan.id, distant.id)
    # Logan nunca teve nenhum conhecimento vivo sobre `distant`.

    view = get_map_view(db_session, campaign.id, logan.id)

    location = next((item for item in view.locations if item.id == distant.id), None)
    assert location is not None
    assert location.source == "map"
    assert location.x == distant.x
    assert location.y == distant.y


def test_map_only_location_never_appears_without_an_owned_map(db_session):
    campaign = create_campaign(db_session, "Sem Mapa Nenhum", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    hidden = Location(region_id=region.id, name="Local Oculto", type="generic")
    db_session.add(hidden)
    db_session.flush()

    view = get_map_view(db_session, campaign.id, character.id)

    assert all(item.id != hidden.id for item in view.locations)


def test_live_knowledge_takes_precedence_over_an_owned_map(db_session):
    campaign = create_campaign(db_session, "Conhecimento Vivo Tem Prioridade", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    # Logan já conhece `village` fisicamente (chegou lá via seed) — mesmo
    # que ele também viesse a possuir um mapa cobrindo o mesmo local, o
    # sinal vivo (discovery) tem prioridade sobre o snapshot congelado.
    set_location_discovery(db_session, logan.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, logan.id)

    location = next(item for item in view.locations if item.id == village.id)
    assert location.source == "discovery"


def test_map_only_location_source_field_is_map(db_session):
    campaign = create_campaign(db_session, "Fonte Mapa", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    cartographer = create_character(db_session, campaign.id, "Mira", region.id, village.id)
    logan = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    distant = Location(region_id=region.id, name="Rowan", type="settlement", x=1, y=1)
    db_session.add(distant)
    db_session.flush()
    _grant(
        db_session, campaign.id, cartographer.id, distant.id,
        GeographicKnowledgeAspect.EXISTENCE, "Um povoado existe.", GeographicPrecision.VAGUE,
    )
    _grant(
        db_session, campaign.id, cartographer.id, distant.id,
        GeographicKnowledgeAspect.DIRECTION, "Fica a leste.", GeographicPrecision.VAGUE,
    )
    _create_and_transfer_map(db_session, campaign.id, cartographer.id, logan.id, distant.id)

    view = get_map_view(db_session, campaign.id, logan.id)

    location = next(item for item in view.locations if item.id == distant.id)
    assert location.source == "map"
    assert "EXISTENCE" in location.known_aspects
