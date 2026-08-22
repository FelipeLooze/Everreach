"""Phase 19H — Spatial Validator.

Genuinely new (narrator.py has no database access to check this):
a claim narrating a THIRD-PARTY NPC — not the active interlocutor,
whose presence is already guaranteed by construction via
app.game.npcs.service's own active-interlocutor resolution — as
physically arriving or present at the current scene, when that NPC's
actual authoritative location_id is somewhere else entirely, is
rejected.

Deliberately conservative (spec: "do not overcorrect", and Phase 19G's
own experience: an over-eager check broke real, working narration).
Only fires when the NPC's name opens the sentence AND a presence verb
appears in it — "Mira entra pela porta." matches; "Alguém entra
enquanto Mira trabalha longe dali." does not, since Mira is not the
sentence's own subject. This intentionally under-detects rather than
risks flagging ordinary prose that merely mentions an absent NPC's
name for an unrelated reason.
"""
import re

from sqlalchemy.orm import Session

from app.ai.narrator import _normalized
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator
from app.db.models.npc import NPC

_PRESENCE_VERBS = re.compile(
    r"\b(entra\w*|chega\w*|aparece\w*|surge\w*|caminha\w*|aproxima\w*|"
    r"atravessa\w*|adentr\w*)\b",
    re.IGNORECASE,
)


def _opens_with_name(text: str, name: str) -> bool:
    first_token = re.match(r"\s*[—-]?\s*(\w+)", text)
    if not first_token or not name:
        return False
    return _normalized(first_token.group(1)) == _normalized(name.split()[0])


@register_validator
def validate_spatial_presence(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    if not proposal.location_id:
        return []

    npcs = (
        db.query(NPC)
        .filter(NPC.campaign_id == campaign_id, NPC.alive.is_(True))
        .all()
    )
    if not npcs:
        return []

    violations: list[Violation] = []
    for claim in claims:
        if not _PRESENCE_VERBS.search(claim.text):
            continue
        for npc in npcs:
            if npc.id == proposal.active_npc_id:
                continue
            if not _opens_with_name(claim.text, npc.name):
                continue
            if npc.location_id != proposal.location_id:
                violations.append(
                    Violation(
                        claim_index=claim.index,
                        category=ClaimCategory.AUTHORITATIVE,
                        reason=(
                            f"'{npc.name}' é narrado(a) chegando/presente nesta cena, mas sua "
                            f"localização autoritativa atual é outra."
                        ),
                    )
                )
    return violations
