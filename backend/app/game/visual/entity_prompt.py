"""Phase 23D-N / 23D-R.1 — entity-kind dispatch for automatic prompt
derivation.

The Service API (app.api.routes.visual_assets) never accepts a prompt
from a caller — it only accepts WHAT to generate (entity_type,
entity_id, asset_type), and resolve_generation_inputs is the one place
that turns that into an actual workflow + prompt (+ reference image,
for NPCs with a canonical reference), always derived from
already-established Canon via the same resolvers/builders already
built (23D-G's prompt_builder, resolve_npc_appearance/
resolve_npc_stable_and_current from 21E, build_item_visual_spec from
21D). This is deliberate: a player-supplied free-text prompt would let
a generation ignore Canon entirely — the mirror image of "COMFYUI DOES
NOT DEFINE CANON" (spec, mandatory), which guards the same boundary
from the other direction.

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

23D-R.1 — NPC dispatch now branches on whether a canonical reference
exists (app.game.visual.npc_reference.get_canonical_reference), NEVER
on "any previous portrait exists" or "current asset" or "asset
history" — only the explicitly, deliberately marked canonical
reference (VisualAsset.is_canonical_reference) drives this choice:

  no canonical reference  -> EVERREACH_NPC_PORTRAIT, reference_image=None
  canonical reference set -> EVERREACH_NPC_IDENTITY, reference_image=
                              the reference staged into ComfyUI's own
                              input directory (see asset_storage.
                              stage_reference_image — ComfyUI's
                              LoadImage node cannot resolve a path
                              outside that directory, confirmed by
                              reading ComfyUI's own folder_paths.py)

A canonical reference whose DB row exists but whose file is missing or
unsafe to resolve is a hard failure (NPCReferenceError), never a
silent fallback to a fresh text-to-image generation — an identity edit
that quietly becomes a different face would be a worse outcome than a
clear, typed failure ("COMFYUI FAILURE != GAMEPLAY FAILURE" still
applies: gameplay continues either way, but the caller must be told
the reference-preserving generation specifically could not happen).
"""
import random

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.game.visual.asset_storage import VisualAssetStorageError, resolve_asset_path, stage_reference_image
from app.game.visual.item import build_item_visual_spec
from app.game.visual.npc import resolve_npc_appearance, resolve_npc_stable_and_current
from app.game.visual.npc_reference import NPCReferenceError, get_canonical_reference
from app.game.visual.prompt_builder import (
    build_item_prompt,
    build_npc_identity_edit_prompt,
    build_npc_portrait_prompt,
)
from app.game.visual.workflow_registry import get_current_workflow_definition

_SEED_UPPER_BOUND = 2_147_483_647


class UnsupportedGenerationTargetError(ValueError):
    pass


def _resolve_npc_inputs(
    db: Session, campaign_id: str, npc_id: str, *, settings: Settings | None
) -> tuple[str, str, str, str | None]:
    """Returns (workflow_key, workflow_version, prompt_text, reference_image)."""
    reference = get_canonical_reference(db, campaign_id, npc_id)

    if reference is None:
        appearance = resolve_npc_appearance(db, campaign_id, npc_id)
        prompt_text = build_npc_portrait_prompt(appearance)
        workflow = get_current_workflow_definition("EVERREACH_NPC_PORTRAIT")
        return workflow.key, workflow.version, prompt_text, None

    try:
        source_path = resolve_asset_path(reference.storage_path, settings=settings)
        if not source_path.is_file():
            raise VisualAssetStorageError(
                f"Canonical reference file not found on disk: {source_path}"
            )
        reference_image = stage_reference_image(source_path, asset_id=reference.id, settings=settings)
    except VisualAssetStorageError as exc:
        raise NPCReferenceError(
            f"Canonical reference for NPC {npc_id!r} (asset {reference.id!r}) is unavailable: {exc}"
        ) from exc

    stable, current = resolve_npc_stable_and_current(db, campaign_id, npc_id)
    prompt_text = build_npc_identity_edit_prompt(stable, current)
    workflow = get_current_workflow_definition("EVERREACH_NPC_IDENTITY")
    return workflow.key, workflow.version, prompt_text, reference_image


def resolve_generation_inputs(
    db: Session,
    campaign_id: str,
    entity_type: str,
    entity_id: str,
    asset_type: str,
    *,
    settings: Settings | None = None,
) -> tuple[str, str, str, int, str | None]:
    """Returns (workflow_key, workflow_version, prompt_text, seed,
    reference_image) for a supported (entity_type, asset_type) pair.
    Raises UnsupportedGenerationTargetError for anything else, and
    whatever typed error the underlying resolver raises
    (NPCVisualIdentityError, ItemVisualIdentityError,
    NPCReferenceError, ...) if the entity or its canonical reference is
    not in a usable state — callers should let those surface as HTTP
    errors, not swallow them."""
    if entity_type == "npc" and asset_type == "NPC_PORTRAIT":
        workflow_key, workflow_version, prompt_text, reference_image = _resolve_npc_inputs(
            db, campaign_id, entity_id, settings=settings
        )
    elif entity_type == "item_instance" and asset_type == "ITEM_ILLUSTRATION":
        item_spec = build_item_visual_spec(db, entity_id)
        prompt_text = build_item_prompt(item_spec)
        workflow = get_current_workflow_definition("EVERREACH_ITEM")
        workflow_key, workflow_version, reference_image = workflow.key, workflow.version, None
    else:
        raise UnsupportedGenerationTargetError(
            f"No automatic prompt derivation for entity_type={entity_type!r}, "
            f"asset_type={asset_type!r}."
        )

    seed = random.randint(1, _SEED_UPPER_BOUND)
    return workflow_key, workflow_version, prompt_text, seed, reference_image
