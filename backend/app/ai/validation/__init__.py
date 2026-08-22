"""Phase 19 — Narrative Validator & Canon Guard.

Importing this package registers every validator module (each uses
app.ai.validation.contract.register_validator as a decorator on import)
— callers only ever need `from app.ai.validation import
validate_narrative_proposal`, never a hand-maintained validator list.
"""
from app.ai.validation.contract import (
    NarrativeProposal,
    NarrativeValidationResult,
    Violation,
    validate_narrative_proposal,
)
from app.ai.validation import agency  # noqa: F401 — Phase 19D
from app.ai.validation import canon  # noqa: F401 — Phase 19F
from app.ai.validation import knowledge  # noqa: F401 — Phase 19G
from app.ai.validation import spatial  # noqa: F401 — Phase 19H
from app.ai.validation import capability  # noqa: F401 — Phase 19I
from app.ai.validation import currency  # noqa: F401 — Phase 19J
from app.ai.validation import npc_state  # noqa: F401 — Phase 19K
from app.ai.validation import organizations  # noqa: F401 — Phase 19L
from app.ai.validation import temporal  # noqa: F401 — Phase 19M
from app.ai.validation import mechanical  # noqa: F401 — Phase 19N
from app.ai.validation import persistent  # noqa: F401 — Phase 19O

__all__ = [
    "NarrativeProposal",
    "NarrativeValidationResult",
    "Violation",
    "validate_narrative_proposal",
]
