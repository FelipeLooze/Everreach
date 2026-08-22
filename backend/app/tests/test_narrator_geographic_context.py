"""Phase 17P — System / Narrator Context."""

from app.ai.context_builder import build_context
from app.core.enums import GeographicKnowledgeAspect, KnowerType
from app.db.models.location import Location
from app.db.models.subregion import Subregion
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.knowledge.maps import character_maps_covering, create_map
from app.game.world.seed import create_campaign, seed_initial_region


def _grant_mappable_knowledge(db_session, campaign_id, character_id, subject_kind, entity_id):
    for aspect, statement in [
        (GeographicKnowledgeAspect.EXISTENCE, "Uma grande cidade existe ao sul."),
        (GeographicKnowledgeAspect.DIRECTION, "Fica ao sul de Cardal."),
    ]:
        ensure_geographic_fact(db_session, campaign_id, subject_kind, entity_id, aspect, statement)
        grant_geographic_knowledge(db_session, campaign_id, KnowerType.PLAYER, character_id, subject_kind, entity_id, aspect)


def test_known_subregion_facts_surface_in_narrator_context(db_session):
    campaign = create_campaign(db_session, "Contexto Subregiao", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)

    subregion_id = db_session.get(Location, village.id).subregion_id
    ensure_geographic_fact(
        db_session, campaign.id, "subregion", subregion_id, GeographicKnowledgeAspect.DANGERS,
        "Bandidos assaltam viajantes com frequência nesta área.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, character.id,
        "subregion", subregion_id, GeographicKnowledgeAspect.DANGERS,
    )

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state)

    assert "Bandidos assaltam viajantes" in context


def test_unknown_subregion_facts_never_leak_into_narrator_context(db_session):
    campaign = create_campaign(db_session, "Contexto Sem Vazamento", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)

    subregion_id = db_session.get(Location, village.id).subregion_id
    ensure_geographic_fact(
        db_session, campaign.id, "subregion", subregion_id, GeographicKnowledgeAspect.DANGERS,
        "Uma criatura territorial rara vive nas colinas próximas.",
    )
    # Deliberately never granted to the player.

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state)

    assert "criatura territorial rara" not in context


def test_character_maps_covering_finds_only_owned_maps_of_that_entity(db_session):
    campaign = create_campaign(db_session, "Mapas Do Personagem", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)
    _grant_mappable_knowledge(db_session, campaign.id, character.id, "settlement", "loc_arven")

    create_map(db_session, campaign.id, character.id, "settlement", "loc_arven")

    covering = character_maps_covering(db_session, character.id, "settlement", "loc_arven")
    assert len(covering) == 1

    not_covering = character_maps_covering(db_session, character.id, "settlement", "loc_somewhere_else")
    assert not_covering == []
