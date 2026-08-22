"""Phase 20C — Knowledge-Aware Rendering."""

from app.core.enums import DiscoveryStatus, GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.knowledge.geography import ensure_geographic_fact, geographic_fact_key, grant_fact_with_precision
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def _grant(db_session, campaign_id, character_id, location_id, aspect, statement, precision=GeographicPrecision.VAGUE):
    ensure_geographic_fact(db_session, campaign_id, "location", location_id, aspect, statement)
    grant_fact_with_precision(
        db_session, campaign_id,
        geographic_fact_key("location", location_id, aspect),
        KnowerType.PLAYER, character_id, precision=precision,
    )


def test_location_known_only_through_a_knowledge_grant_still_appears(db_session):
    """The core 20C gap: an NPC saying 'Arven exists far south' grants
    only a KnowledgeFact, never a CharacterLocationDiscovery row — the
    location must still surface in the Map View."""
    campaign = create_campaign(db_session, "Conhecimento Sem Descoberta", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    distant = Location(region_id=region.id, name="Arven", type="settlement", x=9000, y=1)
    db_session.add(distant)
    db_session.flush()
    # Nenhum CharacterLocationDiscovery para `distant`.
    _grant(db_session, campaign.id, character.id, distant.id, GeographicKnowledgeAspect.EXISTENCE, "Arven existe.")

    view = get_map_view(db_session, campaign.id, character.id)

    location = next((item for item in view.locations if item.id == distant.id), None)
    assert location is not None
    assert location.discovery_status == DiscoveryStatus.RUMORED.value
    assert "EXISTENCE" in location.known_aspects


def test_location_with_no_existence_signal_never_appears(db_session):
    campaign = create_campaign(db_session, "Sem Sinal Nenhum", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    hidden = Location(region_id=region.id, name="Local Oculto", type="generic")
    db_session.add(hidden)
    db_session.flush()

    view = get_map_view(db_session, campaign.id, character.id)

    assert all(item.id != hidden.id for item in view.locations)


def test_known_aspects_reflect_only_what_is_actually_known(db_session):
    """'knows place exists' must not silently become 'knows exact map
    pin' — known_aspects should list EXISTENCE and DIRECTION here, but
    never ROUTE or the position-revealing aspects."""
    campaign = create_campaign(db_session, "Aspectos Conhecidos", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    distant = Location(region_id=region.id, name="Dorn", type="settlement", x=42, y=99)
    db_session.add(distant)
    db_session.flush()
    # Note: statements deliberately never mention "Dorn" itself — the
    # canonical name must stay hidden until the NAME aspect is granted,
    # not leak through explicitly_knows_name's substring check (17A).
    _grant(db_session, campaign.id, character.id, distant.id, GeographicKnowledgeAspect.EXISTENCE, "Um povoado existe por ali.")
    _grant(db_session, campaign.id, character.id, distant.id, GeographicKnowledgeAspect.DIRECTION, "Fica a nordeste.")

    view = get_map_view(db_session, campaign.id, character.id)

    location = next(item for item in view.locations if item.id == distant.id)
    assert set(location.known_aspects) == {"EXISTENCE", "DIRECTION"}
    assert location.x is None
    assert location.y is None


def test_visited_location_reports_at_least_existence_aspect(db_session):
    campaign = create_campaign(db_session, "Visitado Sempre Existe", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id)

    location = next(item for item in view.locations if item.id == village.id)
    assert "EXISTENCE" in location.known_aspects


def test_phase17_only_location_pulls_in_its_region(db_session):
    campaign = create_campaign(db_session, "Regiao Trazida Junto", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    other_region_location = Location(region_id=region.id, name="Rowan", type="settlement", x=1, y=1)
    db_session.add(other_region_location)
    db_session.flush()
    _grant(
        db_session, campaign.id, character.id, other_region_location.id,
        GeographicKnowledgeAspect.EXISTENCE, "Rowan existe.",
    )

    view = get_map_view(db_session, campaign.id, character.id)

    assert any(reg.id == region.id for reg in view.regions)
