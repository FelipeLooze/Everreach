"""Phase 16U — Knowledge & Discovery Boundaries."""

from app.api.serializers import to_game_state_response
from app.core.enums import KnowerType
from app.db.models.knowledge import KnowledgeFact
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.npcs.service import teach_fact
from app.game.world.boundaries import create_regional_boundary
from app.game.world.cross_region_routes import connect_boundary_to_neighbor_region
from app.game.world.neighbor_region import materialize_neighbor_region
from app.game.world.region_discovery import grant_rumor_of_neighbor_region
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session, world_seed):
    campaign = create_campaign(db_session, f"Descoberta {world_seed}", world_seed=world_seed)
    source_region, village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)
    neighbor = materialize_neighbor_region(db_session, campaign.id, boundary, region_index=1)
    connect_boundary_to_neighbor_region(db_session, boundary, neighbor)
    character = create_character(
        db_session, campaign.id, "Logan", region_id=source_region.id, location_id=village.id
    )
    return campaign, source_region, boundary, neighbor, character


def test_rumor_mentions_the_boundary_but_never_the_regions_real_name(db_session):
    campaign, _source, boundary, neighbor, character = _setup(db_session, 800)

    grant_rumor_of_neighbor_region(db_session, campaign.id, character.id, boundary)

    fact = (
        db_session.query(KnowledgeFact)
        .filter(KnowledgeFact.campaign_id == campaign.id, KnowledgeFact.fact_key == f"neighbor_rumor:{boundary.id}")
        .one()
    )
    assert boundary.name in fact.statement
    assert neighbor.name not in fact.statement


def test_neighbor_region_name_stays_hidden_even_while_the_character_is_standing_in_it(db_session):
    campaign, _source, _boundary, neighbor, character = _setup(db_session, 801)

    neighbor_location = (
        db_session.query(Location).filter(Location.region_id == neighbor.id).first()
    )
    character.region_id = neighbor.id
    character.location_id = neighbor_location.id
    db_session.flush()

    state = build_game_state(db_session, campaign.id, character.id)
    response = to_game_state_response(db_session, state)

    assert response.region is not None
    assert response.region.id == neighbor.id
    assert response.region.name is None
    assert response.region.discovery_status == "RUMORED"


def test_granting_only_the_vague_rumor_does_not_reveal_the_real_name(db_session):
    campaign, _source, boundary, neighbor, character = _setup(db_session, 802)

    character.region_id = neighbor.id
    db_session.flush()

    grant_rumor_of_neighbor_region(db_session, campaign.id, character.id, boundary)

    state = build_game_state(db_session, campaign.id, character.id)
    response = to_game_state_response(db_session, state)

    assert response.region.name is None


def test_explicitly_teaching_the_real_name_does_reveal_it(db_session):
    campaign, _source, _boundary, neighbor, character = _setup(db_session, 803)

    character.region_id = neighbor.id
    db_session.flush()

    fact_key = "test_neighbor_name_revealed"
    db_session.add(
        KnowledgeFact(
            campaign_id=campaign.id,
            subject=f"region:{neighbor.id}",
            fact_key=fact_key,
            statement=f"{neighbor.name} é o nome do território além da fronteira.",
        )
    )
    db_session.flush()
    teach_fact(db_session, campaign.id, fact_key, KnowerType.PLAYER, character.id)

    state = build_game_state(db_session, campaign.id, character.id)
    response = to_game_state_response(db_session, state)

    assert response.region.name == neighbor.name
