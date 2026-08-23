"""Phase 23D-G — VisualSpec Builder Foundation.

"VISUAL SPEC != IMAGE PROMPT" (spec.py's own mandatory rule, Phase
21C): this module is exactly the disposable, ComfyUI-adjacent step that
docstring anticipated — it only ever READS already-resolved visual data
(ItemVisualSpec from app.game.visual.item, resolve_npc_appearance's
dict from app.game.visual.npc) and turns it into prompt text. It never
stores anything, never decides what an item/NPC looks like, and is
never the other direction: Canon is never derived from prompt text.

Item prompts can be built from real structured fields because item
Canon (type/weapon_family/material/quality/condition) is a closed,
known vocabulary (Phase 10). NPC prompts deliberately do NOT do the
same per-key templating: app.game.visual.spec's own stable/current
dict keys are explicitly unenumerated ("nothing here validates or
hard-codes field names, on purpose") — inventing a phrase template per
possible key would be exactly the hardcoded vocabulary that design
choice rejected. Instead, an NPC prompt is built generically from
whatever trait VALUES the resolved appearance actually has (they are
already natural-language fragments — see e.g. app/tests/
test_npc_visual_identity.py's "red", "green", "ceremonial silk").

None of this is expected to be flawless art direction on the first
try — that is exactly what VisualAsset.validation_status=UNREVIEWED
(23D-E) exists for. Nothing downstream may treat a generated asset as
canon-worthy until a later human review (23D-M) marks it VALID.

The three approved style suffixes below are copied VERBATIM from the
hand-calibrated, human-approved workflow graphs (Phase 23B final
baseline / 23C), not re-derived — see app.game.visual.workflow_registry
for exactly which files they came from.
"""
import copy

from app.game.visual.item import ItemVisualSpec

_ITEM_QUALITY_CRAFTSMANSHIP: dict[str, str] = {
    "CRUDE": "crude, unrefined craftsmanship with visible imperfections",
    "POOR": "poor, roughly made craftsmanship",
    "STANDARD": "competent everyday craftsmanship, practical and functional construction",
    "GOOD": "good, solid craftsmanship",
    "EXCELLENT": "excellent, refined craftsmanship",
    "MASTERWORK": "masterwork, exceptional and refined craftsmanship",
}

_ITEM_CONDITION_WEAR: dict[str, str] = {
    "EXCELLENT": "pristine, well-maintained condition",
    "GOOD": "good, lightly used condition",
    "WORN": "worn, visibly used condition",
    "DAMAGED": "damaged, showing clear wear and minor damage",
    "CRITICAL": "heavily damaged, near-broken condition",
    "BROKEN": "broken, non-functional condition",
}

# Phase 23B final baseline — EVERREACH_ITEM_STYLE_V3 (APPROVED_MUNDANE_
# BASELINE), copied verbatim from EVERREACH_ITEM_V3_API.json node "20".
_ITEM_STYLE_SUFFIX = (
    " Dark semi-realistic medieval fantasy RPG inventory illustration, "
    "premium illustrated game item artwork, subtly painterly realistic "
    "rendering, convincing hand-illustrated {materials}, muted natural "
    "colors, selective painted highlights, controlled soft shadows, "
    "low-key dramatic fantasy lighting, dark charcoal near-black "
    "textured backdrop, subtle vignette, elegant restrained detail, "
    "atmospheric inventory icon artwork, not a bright product photo, "
    "not evenly lit, not a 3D render"
)

# Phase 23C — copied verbatim from EVERREACH_NPC_PORTRAIT_V1_API.json node "20".
_NPC_PORTRAIT_STYLE_SUFFIX = (
    " Semi-realistic medieval fantasy RPG character illustration, subtly "
    "painterly digital rendering, natural believable human features, soft "
    "illustrated skin rendering, controlled atmospheric lighting, muted "
    "medieval color palette, premium fantasy character artwork, elegant "
    "restrained detail, realistic anatomy with an illustrated finish, not "
    "a photograph, not CGI, not a 3D render, not anime, not cartoon"
)


class VisualPromptBuilderError(Exception):
    """Raised when there is not enough resolved visual data to build a
    prompt, or a workflow graph does not match the expected node shape."""


def _humanize(token: str) -> str:
    return token.replace("_", " ").strip().lower()


def build_item_prompt(item: ItemVisualSpec) -> str:
    subject = _humanize(item.weapon_family) if item.weapon_family else _humanize(item.item_type)
    material_word = item.material.lower() if item.material else None
    material_phrase = f"{material_word} " if material_word else ""

    craftsmanship = _ITEM_QUALITY_CRAFTSMANSHIP.get(item.quality, "ordinary craftsmanship")
    condition_phrase = _ITEM_CONDITION_WEAR.get(item.condition) if item.condition else None

    sentence = f"A single {material_phrase}{subject}, full item visible, isolated and centered, {craftsmanship}"
    if condition_phrase:
        sentence += f", {condition_phrase}"
    if item.signature_ornamentation:
        sentence += f", {item.signature_ornamentation}"
    sentence += (
        f", only one {subject}, no duplicates, not cropped, sufficient padding "
        "around the object, no hands, no person, no text, no watermark, no logo."
    )

    materials_word = f"{material_word} material" if material_word else "material"
    return sentence + _ITEM_STYLE_SUFFIX.format(materials=materials_word)


def build_npc_portrait_prompt(resolved_appearance: dict) -> str:
    if not resolved_appearance:
        raise VisualPromptBuilderError(
            "Cannot build an NPC portrait prompt from an empty resolved appearance."
        )

    descriptors = ", ".join(
        str(value) for _key, value in sorted(resolved_appearance.items()) if value
    )
    sentence = (
        f"A medieval fantasy person, {descriptors}, waist-up portrait, complete "
        "head and shoulders visible, neutral natural expression, no hands "
        "obscuring face, no weapon, only one person, no text, no watermark, no logo."
    )
    return sentence + _NPC_PORTRAIT_STYLE_SUFFIX


def _require_node(graph: dict, node_id: str, expected_class_type: str) -> dict:
    node = graph.get(node_id)
    if node is None or node.get("class_type") != expected_class_type:
        raise VisualPromptBuilderError(
            f"Workflow graph is missing expected node {node_id!r} ({expected_class_type})."
        )
    return node


def inject_workflow_parameters(
    graph: dict,
    *,
    prompt_text: str,
    seed: int,
    filename_prefix: str,
    reference_image: str | None = None,
) -> dict:
    """Return a NEW graph (deep copy — the input is never mutated, since
    callers hold the registry's own loaded dict) with the shared node-id
    convention every trusted Everreach workflow (app.game.visual.
    workflow_registry) follows populated: node "20" (CLIPTextEncode.
    text), "31" (RandomNoise.noise_seed), "41" (SaveImage.
    filename_prefix), and — only when reference_image is given, for
    image-edit workflows like EVERREACH_NPC_IDENTITY — "50"
    (LoadImage.image)."""
    updated = copy.deepcopy(graph)
    _require_node(updated, "20", "CLIPTextEncode")["inputs"]["text"] = prompt_text
    _require_node(updated, "31", "RandomNoise")["inputs"]["noise_seed"] = seed
    _require_node(updated, "41", "SaveImage")["inputs"]["filename_prefix"] = filename_prefix
    if reference_image is not None:
        _require_node(updated, "50", "LoadImage")["inputs"]["image"] = reference_image
    return updated
