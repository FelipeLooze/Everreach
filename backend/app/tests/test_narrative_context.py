"""Phase 24C — Structured Narrative Context.

build_context() (the flat-string function every existing caller uses)
is now a thin wrapper over build_narrative_context(), which returns the
same information as a NarrativeContext dataclass instead of an
anonymous joined string. These tests prove the two stay in lockstep
(no drift between the structured and serialized forms) and that
individual sections are genuinely addressable by name — the actual
value this subphase adds, since a future consumer (relevance grounding,
token-budget trimming) can now read e.g. ctx.active_npc directly
instead of re-parsing "ACTIVE NPC CONTEXT" out of the full text.
"""
from app.ai.context_builder import NarrativeContext, build_context, build_narrative_context
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Narrative Context Test")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.commit()
    return campaign, region, village, character


def test_build_context_matches_build_narrative_context_serialized(db_session):
    campaign, _region, _village, character = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)

    text = build_context(db_session, state, player_input="Olá")
    ctx = build_narrative_context(db_session, state, player_input="Olá")

    assert text == ctx.serialize()


def test_narrative_context_sections_are_individually_addressable(db_session):
    campaign, _region, _village, character = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)

    ctx = build_narrative_context(db_session, state, player_input="Olá")

    assert isinstance(ctx, NarrativeContext)
    assert ctx.player.startswith("CURRENT PLAYER")
    assert character.name in ctx.player
    assert ctx.world.startswith("CURRENT WORLD")
    assert ctx.location.startswith("CANONICAL LOCATION CONTEXT")
    assert ctx.active_npc.startswith("ACTIVE NPC CONTEXT")
    assert ctx.npc_knowledge  # non-empty even with no active NPC
    assert ctx.canon_rule.startswith("CANON RULE")


def test_narrative_context_active_npc_reflects_the_resolved_interlocutor(db_session):
    from app.db.models.npc import NPC

    campaign, _region, village, character = _setup(db_session)
    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").one()
    state = build_game_state(db_session, campaign.id, character.id)

    ctx_no_npc = build_narrative_context(db_session, state, player_input="Olá")
    assert "Name:" not in ctx_no_npc.active_npc

    ctx_with_npc = build_narrative_context(
        db_session, state, active_interlocutor=elder.id, player_input="Olá"
    )
    assert f"Name: {elder.name}" in ctx_with_npc.active_npc


def test_narrative_context_omits_only_the_documented_conditional_sections(db_session):
    # Every section is always present except inventory/combat/regional/
    # local_economy, which are only included when non-empty — this
    # locks in that exact rule (as_sections()'s own docstring/behavior)
    # so a future edit can't silently start dropping an always-on
    # section without a test noticing.
    campaign, _region, _village, character = _setup(db_session)
    state = build_game_state(db_session, campaign.id, character.id)
    ctx = build_narrative_context(db_session, state, player_input="Olá")

    always_on = [
        ctx.player, ctx.world, ctx.location, ctx.perception, ctx.known_routes,
        ctx.current_location_knowledge, ctx.spatial_knowledge, ctx.visible_npcs,
        ctx.active_npc, ctx.active_transported, ctx.organizations, ctx.currency,
        ctx.shops, ctx.npc_knowledge, ctx.player_knowledge, ctx.npc_memories,
        ctx.player_memories, ctx.retrieved_long_term, ctx.input_canon_check,
        ctx.quests, ctx.techniques, ctx.canon_rule,
    ]
    assert all(section for section in always_on)
