"""Phase 17E — Route Knowledge."""

import pytest

from app.core.enums import GeographicKnowledgeAspect, KnowerType
from app.db.models.location import CharacterConnectionDiscovery, LocationConnection
from app.game.character.service import create_character
from app.game.knowledge.geography import knows_geographic_aspect
from app.game.knowledge.routes import grant_route_knowledge
from app.game.travel.service import TravelError, move_character
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session, world_seed):
    campaign = create_campaign(db_session, f"Rotas {world_seed}", world_seed=world_seed)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)
    connection = (
        db_session.query(LocationConnection)
        .filter(LocationConnection.from_location_id == village.id)
        .first()
    )
    return campaign, region, village, character, connection


def test_granting_route_knowledge_to_a_player_gives_both_halves(db_session):
    campaign, _region, _village, character, connection = _setup(db_session, 1)

    grant_route_knowledge(db_session, campaign.id, KnowerType.PLAYER, character.id, connection, source="exploração")

    mechanical = (
        db_session.query(CharacterConnectionDiscovery)
        .filter(
            CharacterConnectionDiscovery.character_id == character.id,
            CharacterConnectionDiscovery.connection_id == connection.id,
        )
        .first()
    )
    assert mechanical is not None

    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.PLAYER, character.id,
        "location", connection.to_location_id, GeographicKnowledgeAspect.ROUTE,
    ) is True


def test_granting_route_knowledge_to_an_npc_is_informational_only(db_session):
    campaign, _region, _village, _character, connection = _setup(db_session, 2)
    npc_id = "npc_hunter_test"

    grant_route_knowledge(db_session, campaign.id, KnowerType.NPC, npc_id, connection, source="conhecimento local")

    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.NPC, npc_id,
        "location", connection.to_location_id, GeographicKnowledgeAspect.ROUTE,
    ) is True

    # No CharacterConnectionDiscovery row was attempted for a non-Character
    # knower (it would violate the FK if it had been).
    mechanical = (
        db_session.query(CharacterConnectionDiscovery)
        .filter(CharacterConnectionDiscovery.connection_id == connection.id)
        .all()
    )
    assert mechanical == []


def test_known_route_becomes_unusable_if_the_connection_is_deactivated(db_session):
    """KNOWN ROUTE != SAFE ROUTE: knowing a route mechanically and
    informationally does not protect it from real world state changes."""
    campaign, _region, village, character, connection = _setup(db_session, 3)

    grant_route_knowledge(db_session, campaign.id, KnowerType.PLAYER, character.id, connection, source="exploração")

    connection.active = False
    db_session.flush()

    with pytest.raises(TravelError):
        move_character(db_session, campaign.id, character, connection.to_location_id)


def test_route_statement_reflects_distance_and_danger_at_grant_time(db_session):
    campaign, _region, _village, character, connection = _setup(db_session, 4)

    from app.db.models.knowledge import KnowledgeFact
    from app.game.knowledge.geography import geographic_fact_key

    connection.distance = 3.5
    connection.danger = 6
    db_session.flush()

    grant_route_knowledge(db_session, campaign.id, KnowerType.PLAYER, character.id, connection, source="exploração")

    fact_key = geographic_fact_key("location", connection.to_location_id, GeographicKnowledgeAspect.ROUTE)
    fact = db_session.query(KnowledgeFact).filter(KnowledgeFact.fact_key == fact_key).one()
    assert "3.5" in fact.statement
    assert "muito perigosa" in fact.statement

    # World state changes afterward never rewrite the already-granted
    # statement — it stays a snapshot from the moment it was learned.
    connection.danger = 0
    db_session.flush()
    assert "muito perigosa" in fact.statement
