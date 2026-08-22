"""Phase 20A — Player Map Data Contract."""

from app.core.enums import DiscoveryStatus, GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.knowledge.geography import ensure_geographic_fact, grant_fact_with_precision, geographic_fact_key
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def test_a_visited_location_is_returned_with_its_name_and_exact_position(db_session):
    campaign = create_campaign(db_session, "Mapa Visitado", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    # Visitar não ensina o nome canônico automaticamente (mesma regra já
    # usada por context_builder.py/o narrador) — precisa de um grant
    # explícito, como uma revelação por diálogo faria de verdade.
    ensure_geographic_fact(
        db_session, campaign.id, "location", village.id,
        GeographicKnowledgeAspect.NAME, f"Este lugar se chama {village.name}.",
    )
    grant_fact_with_precision(
        db_session, campaign.id,
        geographic_fact_key("location", village.id, GeographicKnowledgeAspect.NAME),
        KnowerType.PLAYER, character.id, precision=GeographicPrecision.PRECISE,
    )

    view = get_map_view(db_session, campaign.id, character.id)

    location = next(item for item in view.locations if item.id == village.id)
    assert location.name == village.name
    assert location.x == village.x
    assert location.y == village.y
    assert location.precision == GeographicPrecision.PRECISE.value


def test_an_undiscovered_location_never_appears_in_the_view(db_session):
    campaign = create_campaign(db_session, "Mapa Nao Descoberto", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    hidden = Location(region_id=region.id, name="Vale Escondido", type="generic", x=999, y=999)
    db_session.add(hidden)
    db_session.flush()
    # Nenhum CharacterLocationDiscovery criado para `hidden` — permanece UNKNOWN.

    view = get_map_view(db_session, campaign.id, character.id)

    assert all(item.id != hidden.id for item in view.locations)


def test_raw_authoritative_location_count_is_never_exposed(db_session):
    campaign = create_campaign(db_session, "Mapa Sem Vazar Contagem", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    for index in range(5):
        db_session.add(Location(region_id=region.id, name=f"Local Oculto {index}", type="generic"))
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id)

    assert len(view.locations) == 1
    assert view.locations[0].id == village.id


def test_campaigns_are_isolated(db_session):
    first = create_campaign(db_session, "Mapa Campanha A", world_seed=4)
    second = create_campaign(db_session, "Mapa Campanha B", world_seed=5)
    region_a, village_a = seed_initial_region(db_session, first.id)
    character_a = create_character(db_session, first.id, "Logan", region_a.id, village_a.id)
    set_location_discovery(db_session, character_a.id, village_a.id, DiscoveryStatus.VISITED)

    view_b = get_map_view(db_session, second.id, character_a.id)

    assert view_b.locations == []


def test_two_characters_in_the_same_campaign_can_have_different_map_views(db_session):
    campaign = create_campaign(db_session, "Mapa Por Personagem", world_seed=6)
    region, village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    mira = create_character(db_session, campaign.id, "Mira", region.id, village.id)
    set_location_discovery(db_session, logan.id, village.id, DiscoveryStatus.VISITED)

    logan_view = get_map_view(db_session, campaign.id, logan.id)
    mira_view = get_map_view(db_session, campaign.id, mira.id)

    assert len(logan_view.locations) == 1
    assert mira_view.locations == []


def test_exact_authoritative_position_never_leaks_through_vague_knowledge(db_session):
    """The spec's own required proof: exact world position + vague
    Character Knowledge -> vague Map View, never exact coordinates."""
    campaign = create_campaign(db_session, "Mapa Conhecimento Vago", world_seed=7)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    distant = Location(region_id=region.id, name="Arven", type="settlement", x=12345, y=67890)
    db_session.add(distant)
    db_session.flush()
    set_location_discovery(db_session, character.id, distant.id, DiscoveryStatus.RUMORED)

    ensure_geographic_fact(
        db_session, campaign.id, "location", distant.id,
        GeographicKnowledgeAspect.EXISTENCE, "Arven existe.",
    )
    ensure_geographic_fact(
        db_session, campaign.id, "location", distant.id,
        GeographicKnowledgeAspect.DIRECTION, "Arven fica ao sul.",
    )
    grant_fact_with_precision(
        db_session, campaign.id,
        geographic_fact_key("location", distant.id, GeographicKnowledgeAspect.EXISTENCE),
        KnowerType.PLAYER, character.id, precision=GeographicPrecision.VAGUE,
    )
    grant_fact_with_precision(
        db_session, campaign.id,
        geographic_fact_key("location", distant.id, GeographicKnowledgeAspect.DIRECTION),
        KnowerType.PLAYER, character.id, precision=GeographicPrecision.VAGUE,
    )

    view = get_map_view(db_session, campaign.id, character.id)

    location = next(item for item in view.locations if item.id == distant.id)
    assert location.precision == GeographicPrecision.VAGUE.value
    assert location.x is None
    assert location.y is None
    assert (location.x, location.y) != (distant.x, distant.y)


def test_precise_phase_17_knowledge_reveals_exact_position_even_without_visiting(db_session):
    """A character who never physically walked there (no VISITED/MAPPED
    discovery status) but was taught PRECISE geographic knowledge (a
    good map, careful directions) should still get the exact position —
    precision is the deciding signal, not the older discovery status
    alone."""
    campaign = create_campaign(db_session, "Mapa Precisao Sem Visita", world_seed=8)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    distant = Location(region_id=region.id, name="Rowan", type="settlement", x=555, y=777)
    db_session.add(distant)
    db_session.flush()
    set_location_discovery(db_session, character.id, distant.id, DiscoveryStatus.DISCOVERED)

    ensure_geographic_fact(
        db_session, campaign.id, "location", distant.id,
        GeographicKnowledgeAspect.DISTANCE, "Rowan fica a três dias.",
    )
    grant_fact_with_precision(
        db_session, campaign.id,
        geographic_fact_key("location", distant.id, GeographicKnowledgeAspect.DISTANCE),
        KnowerType.PLAYER, character.id, precision=GeographicPrecision.PRECISE,
    )

    view = get_map_view(db_session, campaign.id, character.id)

    location = next(item for item in view.locations if item.id == distant.id)
    assert location.precision == GeographicPrecision.PRECISE.value
    assert location.x == distant.x
    assert location.y == distant.y


def test_location_name_hidden_until_the_name_aspect_is_known(db_session):
    campaign = create_campaign(db_session, "Mapa Nome Oculto", world_seed=9)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    distant = Location(region_id=region.id, name="Dorn", type="settlement", x=1, y=1)
    db_session.add(distant)
    db_session.flush()
    set_location_discovery(db_session, character.id, distant.id, DiscoveryStatus.RUMORED)
    ensure_geographic_fact(
        db_session, campaign.id, "location", distant.id,
        GeographicKnowledgeAspect.EXISTENCE, "Um lugar existe a leste.",
    )
    grant_fact_with_precision(
        db_session, campaign.id,
        geographic_fact_key("location", distant.id, GeographicKnowledgeAspect.EXISTENCE),
        KnowerType.PLAYER, character.id, precision=GeographicPrecision.VAGUE,
    )

    view = get_map_view(db_session, campaign.id, character.id)

    location = next(item for item in view.locations if item.id == distant.id)
    assert location.name is None
