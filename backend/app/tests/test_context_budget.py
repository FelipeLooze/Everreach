"""Phase 24M — Context Priority & Token Budgeting.

apply_context_budget() is the one GLOBAL ceiling on context_builder's
combined output — distinct from every existing per-field clip and from
Phase 18L's own retrieval-tail budget. These tests exercise it directly
against a synthetic NarrativeContext (not a real campaign — a real
scene's context virtually never approaches 20000 chars, so a live DB
fixture couldn't force an over-budget case without an unrealistic
amount of fixture data).
"""
from app.ai.context_builder import (
    MAX_CONTEXT_BUDGET_CHARS,
    NarrativeContext,
    apply_context_budget,
)


def _ctx(**overrides) -> NarrativeContext:
    base = dict(
        player="CURRENT PLAYER\nName: Logan",
        inventory="",
        world="CURRENT WORLD\nYear 1",
        location="CANONICAL LOCATION CONTEXT\nName: Cardal",
        perception="PERCEPTION\n- none",
        known_routes="KNOWN ROUTES\n- none",
        current_location_knowledge="CURRENT LOCATION KNOWLEDGE\n- none",
        spatial_knowledge="SPATIAL KNOWLEDGE\n- none",
        visible_npcs="VISIBLE NPCS\n- none",
        combat="",
        active_npc="ACTIVE NPC CONTEXT\nName: Aldric",
        active_transported="ACTIVE TRANSPORTED PERSON CONTEXT\n- none",
        organizations="ORGANIZATIONS\n- none",
        currency="CURRENCY\n- none",
        regional="",
        local_economy="",
        shops="SHOPS\n- none",
        npc_knowledge="NPC KNOWLEDGE\n- none",
        player_knowledge="PLAYER KNOWLEDGE\n- none",
        npc_memories="RELEVANT NPC MEMORIES\n- none",
        player_memories="RELEVANT PLAYER MEMORIES\n- none",
        retrieved_long_term="RELEVANT LONG-TERM KNOWLEDGE\n- none",
        input_canon_check="PLAYER INPUT CANON CHECK\n- none",
        quests="ACTIVE QUESTS\n- none",
        techniques="KNOWN TECHNIQUES\n- none",
        canon_rule="CANON RULE\n...",
    )
    base.update(overrides)
    return NarrativeContext(**base)


def test_under_budget_context_is_returned_unchanged():
    ctx = _ctx()
    result = apply_context_budget(ctx, budget_chars=MAX_CONTEXT_BUDGET_CHARS)

    assert result.context is ctx
    assert result.dropped_sections == ()
    assert result.used_chars == len(ctx.serialize())


def test_over_budget_drops_lowest_priority_section_first():
    ctx = _ctx(retrieved_long_term="RELEVANT LONG-TERM KNOWLEDGE\n" + "x" * 25000)
    result = apply_context_budget(ctx, budget_chars=5000)

    assert result.dropped_sections == ("retrieved_long_term",)
    assert result.context.retrieved_long_term == ""
    assert result.used_chars <= 5000


def test_mandatory_sections_are_never_dropped_even_far_over_budget():
    # Even an impossible-to-satisfy budget must never touch mandatory
    # sections — it drops everything droppable and stops, rather than
    # reaching into player/active_npc/npc_knowledge/canon_rule.
    ctx = _ctx(
        retrieved_long_term="x" * 5000,
        regional="x" * 5000,
        local_economy="x" * 5000,
        shops="x" * 5000,
        player_knowledge="x" * 5000,
        player_memories="x" * 5000,
        npc_memories="x" * 5000,
    )
    result = apply_context_budget(ctx, budget_chars=10)

    assert set(result.dropped_sections) == {
        "retrieved_long_term", "regional", "local_economy", "shops",
        "player_knowledge", "player_memories", "npc_memories",
    }
    assert result.context.player == ctx.player
    assert result.context.active_npc == ctx.active_npc
    assert result.context.npc_knowledge == ctx.npc_knowledge
    assert result.context.canon_rule == ctx.canon_rule
    assert result.context.location == ctx.location


def test_drops_stop_as_soon_as_budget_is_satisfied():
    # Only the sections actually needed to get under budget are dropped
    # — a small overage must not cascade into dropping everything.
    ctx = _ctx(retrieved_long_term="x" * 500)
    small_overage_budget = len(ctx.serialize()) - 100
    result = apply_context_budget(ctx, budget_chars=small_overage_budget)

    assert result.dropped_sections == ("retrieved_long_term",)
    assert result.context.regional == ctx.regional
    assert result.context.local_economy == ctx.local_economy


def test_empty_droppable_sections_are_skipped_not_counted_as_dropped():
    # retrieved_long_term is already empty (nothing to drop there) — the
    # budget must move on to the next droppable field instead of
    # reporting a no-op drop.
    ctx = _ctx(retrieved_long_term="", regional="x" * 25000)
    result = apply_context_budget(ctx, budget_chars=5000)

    assert result.dropped_sections == ("regional",)
