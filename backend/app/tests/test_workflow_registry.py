"""Phase 23D-C — Visual Workflow Registry."""
import json

import pytest

from app.core.config import Settings
from app.game.visual.spec import FUTURE_ASSET_KINDS
from app.game.visual.workflow_registry import (
    VisualWorkflowRegistryError,
    WorkflowDefinition,
    WorkflowFileMissingError,
    WorkflowNotFoundError,
    get_current_workflow_definition,
    get_workflow_definition,
    list_workflows,
    load_workflow_graph,
)


def test_every_registered_workflow_declares_a_known_asset_type():
    for workflow in list_workflows():
        assert workflow.produces_asset_type in FUTURE_ASSET_KINDS


def test_workflow_definition_rejects_unknown_asset_type():
    with pytest.raises(VisualWorkflowRegistryError):
        WorkflowDefinition(
            key="BOGUS", version="V1", produces_asset_type="NOT_A_REAL_KIND",
            filename="bogus.json", is_current=True, description="",
        )


def test_get_workflow_definition_returns_known_entry():
    workflow = get_workflow_definition("EVERREACH_ITEM", "V3")
    assert workflow.filename == "EVERREACH_ITEM_V3_API.json"
    assert workflow.is_current is True


def test_get_workflow_definition_raises_for_unknown_key_or_version():
    with pytest.raises(WorkflowNotFoundError):
        get_workflow_definition("EVERREACH_ITEM", "V99")
    with pytest.raises(WorkflowNotFoundError):
        get_workflow_definition("NOT_A_WORKFLOW", "V1")


def test_get_current_workflow_definition_returns_the_approved_baseline():
    current = get_current_workflow_definition("EVERREACH_ITEM")
    assert current.version == "V3"


def test_superseded_item_versions_stay_resolvable_but_are_not_current():
    v1 = get_workflow_definition("EVERREACH_ITEM", "V1")
    v2 = get_workflow_definition("EVERREACH_ITEM", "V2")
    assert v1.is_current is False
    assert v2.is_current is False


def test_get_current_workflow_definition_raises_for_unknown_key():
    with pytest.raises(WorkflowNotFoundError):
        get_current_workflow_definition("NOT_A_WORKFLOW")


def test_load_workflow_graph_reads_and_parses_the_file(tmp_path):
    graph = {"1": {"class_type": "SaveImage", "inputs": {}}}
    (tmp_path / "EVERREACH_ITEM_V3_API.json").write_text(json.dumps(graph), encoding="utf-8")
    settings = Settings(comfyui_workflow_root=str(tmp_path))

    loaded = load_workflow_graph("EVERREACH_ITEM", "V3", settings=settings)

    assert loaded == graph


def test_load_workflow_graph_raises_when_file_is_missing_on_disk(tmp_path):
    settings = Settings(comfyui_workflow_root=str(tmp_path))

    with pytest.raises(WorkflowFileMissingError):
        load_workflow_graph("EVERREACH_ITEM", "V3", settings=settings)


def test_load_workflow_graph_raises_when_root_is_not_configured():
    settings = Settings(comfyui_workflow_root="")

    with pytest.raises(VisualWorkflowRegistryError):
        load_workflow_graph("EVERREACH_ITEM", "V3", settings=settings)


def test_load_workflow_graph_raises_for_unregistered_workflow(tmp_path):
    settings = Settings(comfyui_workflow_root=str(tmp_path))

    with pytest.raises(WorkflowNotFoundError):
        load_workflow_graph("NOT_A_WORKFLOW", "V1", settings=settings)
