"""Phase 23D-G — VisualSpec Builder Foundation."""
import pytest

from app.game.visual.item import ItemVisualSpec
from app.game.visual.prompt_builder import (
    VisualPromptBuilderError,
    build_item_prompt,
    build_npc_portrait_prompt,
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
