"""Phase 23D-G — VisualSpec Builder Foundation."""
import pytest

from app.game.visual.item import ItemVisualSpec
from app.game.visual.prompt_builder import (
    VisualPromptBuilderError,
    build_item_prompt,
    build_npc_identity_edit_prompt,
    build_npc_portrait_prompt,
    extract_model_identifier,
    inject_workflow_parameters,
)


def _item(**overrides) -> ItemVisualSpec:
    params = dict(
        item_instance_id="item_1",
        definition_id="def_1",
        name="Steel Longsword",
        item_type="WEAPON",
        weapon_family="LONGSWORD",
        material="steel",
        quality="STANDARD",
        condition="GOOD",
        equipped_slot=None,
        signature_ornamentation=None,
        asset_ref=None,
    )
    params.update(overrides)
    return ItemVisualSpec(**params)


def test_build_item_prompt_includes_weapon_family_material_and_craftsmanship():
    prompt = build_item_prompt(_item())

    assert "longsword" in prompt
    assert "steel" in prompt
    assert "competent everyday craftsmanship" in prompt
    assert "good, lightly used condition" in prompt


def test_build_item_prompt_falls_back_to_item_type_without_weapon_family():
    prompt = build_item_prompt(_item(weapon_family=None, item_type="TOOL"))

    assert "tool" in prompt
    assert "longsword" not in prompt


def test_build_item_prompt_includes_signature_ornamentation_when_present():
    prompt = build_item_prompt(_item(signature_ornamentation="a faint pale-blue engraved line along the blade"))

    assert "a faint pale-blue engraved line along the blade" in prompt


def test_build_item_prompt_omits_ornamentation_clause_when_absent():
    prompt = build_item_prompt(_item(signature_ornamentation=None))

    assert "engraved" not in prompt


def test_build_item_prompt_ends_with_the_approved_style_suffix_verbatim():
    prompt = build_item_prompt(_item())

    assert prompt.endswith(
        "not evenly lit, not a 3D render"
    )
    assert "Dark semi-realistic medieval fantasy RPG inventory illustration" in prompt


def test_build_npc_portrait_prompt_includes_every_trait_value():
    prompt = build_npc_portrait_prompt(
        {"hair_color": "dark auburn red", "eye_color": "green", "permanent_scar": "left cheek"}
    )

    assert "dark auburn red" in prompt
    assert "green" in prompt
    assert "left cheek" in prompt
    assert "Semi-realistic medieval fantasy RPG character illustration" in prompt


def test_build_npc_portrait_prompt_raises_for_empty_appearance():
    with pytest.raises(VisualPromptBuilderError):
        build_npc_portrait_prompt({})


def test_build_npc_portrait_prompt_skips_falsy_values():
    prompt = build_npc_portrait_prompt({"hair_color": "red", "note": "", "tattoo": None})

    assert prompt.count("red") == 1


def _fake_graph() -> dict:
    return {
        "20": {"class_type": "CLIPTextEncode", "inputs": {"text": "placeholder"}},
        "31": {"class_type": "RandomNoise", "inputs": {"noise_seed": 1}},
        "41": {"class_type": "SaveImage", "inputs": {"filename_prefix": "placeholder"}},
        "50": {"class_type": "LoadImage", "inputs": {"image": "placeholder.png"}},
    }


def test_inject_workflow_parameters_sets_text_seed_and_prefix():
    graph = _fake_graph()

    updated = inject_workflow_parameters(
        graph, prompt_text="a prompt", seed=5002, filename_prefix="everreach/test"
    )

    assert updated["20"]["inputs"]["text"] == "a prompt"
    assert updated["31"]["inputs"]["noise_seed"] == 5002
    assert updated["41"]["inputs"]["filename_prefix"] == "everreach/test"


def test_inject_workflow_parameters_does_not_mutate_the_input_graph():
    graph = _fake_graph()

    inject_workflow_parameters(graph, prompt_text="a prompt", seed=5002, filename_prefix="everreach/test")

    assert graph["20"]["inputs"]["text"] == "placeholder"


def test_inject_workflow_parameters_sets_reference_image_only_when_given():
    graph = _fake_graph()

    without_reference = inject_workflow_parameters(
        graph, prompt_text="a prompt", seed=1, filename_prefix="x"
    )
    with_reference = inject_workflow_parameters(
        graph, prompt_text="a prompt", seed=1, filename_prefix="x", reference_image="canonical_v1.png"
    )

    assert without_reference["50"]["inputs"]["image"] == "placeholder.png"
    assert with_reference["50"]["inputs"]["image"] == "canonical_v1.png"


def test_inject_workflow_parameters_raises_for_a_missing_node():
    graph = _fake_graph()
    del graph["20"]

    with pytest.raises(VisualPromptBuilderError):
        inject_workflow_parameters(graph, prompt_text="a prompt", seed=1, filename_prefix="x")


def test_inject_workflow_parameters_raises_when_node_class_type_does_not_match():
    graph = _fake_graph()
    graph["31"]["class_type"] = "SomethingElse"

    with pytest.raises(VisualPromptBuilderError):
        inject_workflow_parameters(graph, prompt_text="a prompt", seed=1, filename_prefix="x")


def test_build_npc_identity_edit_prompt_preserves_stable_and_depicts_current():
    prompt = build_npc_identity_edit_prompt(
        stable={"hair_color": "silver", "eye_color": "blue"},
        current={"clothing": "a travel cloak"},
    )

    assert "silver" in prompt
    assert "blue" in prompt
    assert "a travel cloak" in prompt
    assert "Same person" in prompt
    assert "keep their exact facial identity" in prompt


def test_build_npc_identity_edit_prompt_never_analyzes_an_image():
    """Structural proof, not just a naming convention: the function
    signature itself has no image/file parameter, so there is nothing
    it COULD read pixels from — every word in its output traces back to
    the stable/current dicts passed in."""
    import inspect

    signature = inspect.signature(build_npc_identity_edit_prompt)
    assert set(signature.parameters) == {"stable", "current"}


def test_build_npc_identity_edit_prompt_raises_for_empty_input():
    with pytest.raises(VisualPromptBuilderError):
        build_npc_identity_edit_prompt(stable={}, current={})


def test_build_npc_identity_edit_prompt_works_with_only_stable_traits():
    prompt = build_npc_identity_edit_prompt(stable={"hair_color": "silver"}, current={})

    assert "silver" in prompt
    assert "Same person" in prompt


def test_build_npc_identity_edit_prompt_does_not_append_the_portrait_style_suffix():
    """The real, human-calibrated 23C identity-edit prompts don't use
    the text-to-image style suffix — matching that baseline exactly."""
    prompt = build_npc_identity_edit_prompt(stable={"hair_color": "silver"}, current={})

    assert "Semi-realistic medieval fantasy RPG character illustration" not in prompt


def _real_npc_identity_graph_shape() -> dict:
    """Mirrors the ACTUAL registered EVERREACH_NPC_IDENTITY_V1_API.json
    node-for-node (ids, class_types, wiring) — not a tiny synthetic
    dict. The _everreach_meta incident (23D-Q live validation) proved a
    fixture that is too simple can miss a real integration mistake;
    this fixture exists so inject_workflow_parameters is proven against
    the real graph SHAPE at least once, without requiring the E: drive
    or a live ComfyUI server."""
    return {
        "_everreach_meta": {"workflow_name": "EVERREACH_NPC_IDENTITY", "workflow_version": 1},
        "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-4b.safetensors", "weight_dtype": "default"}},
        "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "flux2", "device": "default"}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "50": {"class_type": "LoadImage", "inputs": {"image": "everreach_tests/npcs/NPC_VISUAL_TEST_001/canonical_v1.png"}},
        "51": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["50", 0], "upscale_method": "nearest-exact", "megapixels": 1.0, "resolution_steps": 1}},
        "52": {"class_type": "GetImageSize", "inputs": {"image": ["51", 0]}},
        "30": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": ["52", 0], "height": ["52", 1], "batch_size": 1}},
        "33": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": ["52", 0], "height": ["52", 1]}},
        "20": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": "placeholder edit instruction"}},
        "21": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["20", 0]}},
        "53": {"class_type": "VAEEncode", "inputs": {"pixels": ["51", 0], "vae": ["12", 0]}},
        "54": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["21", 0], "latent": ["53", 0]}},
        "55": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["20", 0], "latent": ["53", 0]}},
        "34": {"class_type": "CFGGuider", "inputs": {"model": ["10", 0], "positive": ["55", 0], "negative": ["54", 0], "cfg": 1.0}},
        "31": {"class_type": "RandomNoise", "inputs": {"noise_seed": 5101}},
        "32": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "35": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["31", 0], "guider": ["34", 0], "sampler": ["32", 0], "sigmas": ["33", 0], "latent_image": ["30", 0]}},
        "40": {"class_type": "VAEDecode", "inputs": {"samples": ["35", 0], "vae": ["12", 0]}},
        "41": {"class_type": "SaveImage", "inputs": {"images": ["40", 0], "filename_prefix": "everreach_tests/npcs/placeholder"}},
    }


def test_inject_workflow_parameters_against_the_real_identity_workflow_shape():
    graph = _real_npc_identity_graph_shape()
    graph.pop("_everreach_meta", None)  # load_workflow_graph's own job; not this function's

    updated = inject_workflow_parameters(
        graph,
        prompt_text="Same person, keep identity unchanged. Depict travel cloak.",
        seed=424242,
        filename_prefix="everreach/npc/npc_x/NPC_PORTRAIT/vgen_x",
        reference_image="everreach_reference/vasset_ref001.png",
    )

    assert updated["20"]["inputs"]["text"] == "Same person, keep identity unchanged. Depict travel cloak."
    assert updated["31"]["inputs"]["noise_seed"] == 424242
    assert updated["41"]["inputs"]["filename_prefix"] == "everreach/npc/npc_x/NPC_PORTRAIT/vgen_x"
    assert updated["50"]["inputs"]["image"] == "everreach_reference/vasset_ref001.png"
    # Wiring untouched: node 41's own "images" reference must survive unchanged.
    assert updated["41"]["inputs"]["images"] == ["40", 0]
    assert extract_model_identifier(updated) == "flux-2-klein-4b.safetensors"
