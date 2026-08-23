"""Phase 23D-N — entity-kind dispatch for automatic prompt derivation.

The Service API (app.api.routes.visual_assets) never accepts a prompt
from a caller — it only accepts WHAT to generate (entity_type,
entity_id, asset_type), and resolve_generation_inputs is the one place
that turns that into an actual workflow + prompt, always derived from
already-established Canon via the same resolvers/builders already
built (23D-G's prompt_builder, resolve_npc_appearance from 21E,
build_item_visual_spec from 21D). This is deliberate: a player-supplied
free-text prompt would let a generation ignore Canon entirely — the
mirror image of "COMFYUI DOES NOT DEFINE CANON" (spec, mandatory),
which guards the same boundary from the other direction.

Only the entity/asset_type combinations this module explicitly knows
how to resolve are supported; everything else raises
UnsupportedGenerationTargetError rather than guessing at a prompt.

ITEM_ILLUSTRATION is keyed by entity_type="item_instance" (an
ItemInstance id), not "item_definition" — deliberately distinct from
app.game.visual.spec's VisualIdentity storage for items (which is
per-definition, holding only signature_ornamentation). An illustration
should reflect one specific instance's actual quality/condition
(build_item_visual_spec's whole point), which a shared per-definition
asset could not represent for every instance at once.
"""
import random

from sqlalchemy.orm import Session

from app.game.visual.item import build_item_visual_spec
from app.game.visual.npc import resolve_npc_appearance
from app.game.visual.prompt_builder import build_item_prompt, build_npc_portrait_prompt
from app.game.visual.workflow_registry import get_current_workflow_definition

_SEED_UPPER_BOUND = 2_147_483_647


class UnsupportedGenerationTargetError(ValueError):
    pass


def resolve_generation_inputs(
    db: Session, campaign_id: str, entity_type: str, entity_id: str, asset_type: str
) -> tuple[str, str, str, int]:
    """Returns (workflow_key, workflow_version, prompt_text, seed) for a
    supported (entity_type, asset_type) pair. Raises
    UnsupportedGenerationTargetError for anything else, and whatever
    typed error the underlying resolver raises (NPCVisualIdentityError,
    ItemVisualIdentityError, ...) if the entity itself does not exist —
    callers should let those surface as 404s, not swallow them."""
    if entity_type == "npc" and asset_type == "NPC_PORTRAIT":
        appearance = resolve_npc_appearance(db, campaign_id, entity_id)
        prompt_text = build_npc_portrait_prompt(appearance)
        workflow = get_current_workflow_definition("EVERREACH_NPC_PORTRAIT")
    elif entity_type == "item_instance" and asset_type == "ITEM_ILLUSTRATION":
        item_spec = build_item_visual_spec(db, entity_id)
        prompt_text = build_item_prompt(item_spec)
        workflow = get_current_workflow_definition("EVERREACH_ITEM")
    else:
        raise UnsupportedGenerationTargetError(
            f"No automatic prompt derivation for entity_type={entity_type!r}, "
            f"asset_type={asset_type!r}."
        )

    seed = random.randint(1, _SEED_UPPER_BOUND)
    return workflow.key, workflow.version, prompt_text, seed
