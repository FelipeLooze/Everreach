"""Phase 18O — Narrator Retrieval (current-location lore)."""

from app.ai.context_builder import build_context
from app.ai.retrieval.canon import index_location
from app.core.enums import GeographicKnowledgeAspect, KnowerType
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.world.seed import create_campaign, seed_initial_region


def test_narrator_context_includes_known_current_location_lore(db_session):
    campaign = create_campaign(db_session, "Taverna Revisitada", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    village.description = "Uma taverna acolhedora onde Logan já passou por grandes provações."
    db_session.flush()
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    index_location(db_session, village)
    ensure_geographic_fact(
        db_session, campaign.id, "location", village.id,
        GeographicKnowledgeAspect.EXISTENCE, "Existe.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, character.id,
        "location", village.id, GeographicKnowledgeAspect.EXISTENCE,
    )

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state)

    assert "grandes provações" in context


def test_narrator_context_never_surfaces_lore_for_a_location_the_player_never_visited(db_session):
    campaign = create_campaign(db_session, "Local Distante Nao Conhecido", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)

    from app.db.models.location import Location

    distant = Location(
        region_id=region.id, name="Vila Distante",
        description="Segredo de uma vila que Logan nunca visitou.",
    )
    db_session.add(distant)
    db_session.flush()
    index_location(db_session, distant)

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state)

    assert "Segredo de uma vila" not in context


def test_location_lore_candidates_only_include_the_current_location(db_session):
    from app.ai.context_builder import _current_location_lore_candidates

    campaign = create_campaign(db_session, "Apenas Local Atual", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    index_location(db_session, village)
    ensure_geographic_fact(
        db_session, campaign.id, "location", village.id,
        GeographicKnowledgeAspect.EXISTENCE, "Existe.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, character.id,
        "location", village.id, GeographicKnowledgeAspect.EXISTENCE,
    )

    state = build_game_state(db_session, campaign.id, character.id)
    candidates = _current_location_lore_candidates(db_session, state)

    assert candidates
    assert all(document.source_id == village.id for document in candidates)
