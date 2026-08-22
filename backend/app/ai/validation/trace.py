"""Phase 19S — Validation Trace & Observability.

Developer/debug information ONLY — logged at DEBUG level (same
convention app.ai.narrator already uses throughout its own validation
loop: logger.debug("REVIEW RESULT...")), never returned to a caller and
never part of anything that could reach the player. Phase 19D
introduced a real leak of this kind: NarrativeValidationResult.
violations (internal reasons like "'Logan sorri...' atribui uma ação
voluntária...") was being merged into app.game.engine's
ActionResult.warnings, which schemas/action.py exposes verbatim over
the public /actions API — exactly the "CLAIM #4 FAILED" shape the spec
explicitly forbids surfacing to the player. This subphase's engine.py
change removes that merge; the trace below is the correct channel for
this information instead.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    # String-only at runtime (see `from __future__ import annotations`
    # above) so this module never actually imports contract.py — that
    # module is the one that imports and calls this function.
    from app.ai.validation.claims import NarrativeClaim
    from app.ai.validation.contract import NarrativeProposal, Violation

logger = get_logger("narration")


def log_validation_trace(
    proposal: "NarrativeProposal",
    claims: "list[NarrativeClaim]",
    violations: "list[Violation]",
) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return

    violations_by_claim: dict[int, list[Violation]] = {}
    for violation in violations:
        violations_by_claim.setdefault(violation.claim_index, []).append(violation)

    lines = [
        "NARRATIVE VALIDATION TRACE",
        f"Mode: {proposal.mode}",
        f"Active NPC: {proposal.active_npc_name or '(none)'}",
        "",
    ]
    for claim in claims:
        claim_violations = violations_by_claim.get(claim.index, [])
        result = "REJECTED" if claim_violations else "ALLOWED"
        categories = ", ".join(sorted(category.value for category in claim.categories))
        lines.append(f"Claim: {claim.text!r}")
        lines.append(f"Category: {categories}")
        lines.append(f"Result: {result}")
        for violation in claim_violations:
            lines.append(f"Reason: {violation.reason}")
        lines.append("")

    logger.debug("\n".join(lines))
