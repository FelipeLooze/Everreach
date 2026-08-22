"""Phase 15S — Context / Narrator Integration. Closes Phase 15 (15A-15S).

The narrator only ever gets category/adjective-level texture for wherever
the character currently physically is (biome, danger) — never the
subregion's proper name, never any other subregion's data, never a
region-wide dump. WORLD TRUTH != CHARACTER KNOWLEDGE != NARRATIVE CONTEXT
holds even now that the Region is massive (dozens of subregions).
"""

from app.ai import context_builder
from app.core.enums import SubregionBiome
from app.db.models.subregion import Subregion
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.world.content_pools import ANCHOR_SUBREGION_NAME
from app.game.world.seed import create_campaign, seed_initial_region


def test_regional_context_describes_the_characters_current_subregion(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    assert "REGIONAL CONTEXT" in context
    section = context.split("REGIONAL CONTEXT", 1)[1].split("\n\n")[0]
    assert "planícies abertas" in section


def test_regional_context_never_names_the_subregion_or_other_subregions(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)

    other_subregion_names = [
        s.name
        for s in db_session.query(Subregion).filter(Subregion.region_id == region.id).all()
        if s.name != ANCHOR_SUBREGION_NAME
    ]
    assert other_subregion_names  # sanity: the region really is massive

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    assert ANCHOR_SUBREGION_NAME not in context
    for name in other_subregion_names:
        assert name not in context


def test_regional_context_is_empty_when_location_has_no_subregion(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)

    village.subregion_id = None
    db_session.flush()

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    assert "REGIONAL CONTEXT" not in context
