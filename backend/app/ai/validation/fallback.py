"""Phase 19R — Safe Fallback Narration.

Reuses app.ai.narrator._safe_hard_failure_fallback verbatim — the exact
same deterministic, immersive fallback narrator.narrate() already
returns for its own unresolvable-violation case ("Nada acontece de
imediato." / "{npc} permanece em silêncio.") — rather than inventing a
second, divergent fallback convention. Never a developer-facing message
("no mechanical system applies"); always a low-stakes, scene-neutral
narrative beat that controls nothing, invents nothing, and exposes
nothing hidden.

Takes plain primitives (mode, active_npc_name) rather than a
NarrativeProposal to avoid a circular import with contract.py, which
calls this module.
"""
from app.ai.narrator import NarrationMode, _safe_hard_failure_fallback


def safe_fallback_narration(mode: NarrationMode, active_npc_name: str | None) -> str:
    return _safe_hard_failure_fallback(mode, active_npc_name or "")
