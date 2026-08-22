"""Phase 19R — Safe Fallback Narration."""

from app.ai.validation.fallback import safe_fallback_narration


def test_fallback_with_an_active_npc_keeps_them_present_but_silent():
    text = safe_fallback_narration("CONTINUATION", "Osgar")

    assert "Osgar" in text
    assert text.strip()


def test_fallback_without_an_active_npc_is_a_neutral_scene_beat():
    text = safe_fallback_narration("CONTINUATION", None)

    assert text.strip()


def test_fallback_never_reads_as_a_developer_facing_message():
    """The spec explicitly forbids fallback text like 'no mechanical
    system applies' — this checks the two known fallback strings never
    contain obvious developer/system vocabulary."""
    for npc_name in (None, "Osgar"):
        text = safe_fallback_narration("CONTINUATION", npc_name)
        lowered = text.lower()
        for forbidden in ("error", "sistema", "mecânico", "validação", "exception"):
            assert forbidden not in lowered


def test_fallback_is_deterministic_for_the_same_inputs():
    first = safe_fallback_narration("CONTINUATION", "Osgar")
    second = safe_fallback_narration("CONTINUATION", "Osgar")

    assert first == second
