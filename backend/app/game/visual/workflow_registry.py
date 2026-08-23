"""Phase 23D-C — Visual Workflow Registry.

Trusted-workflow-only (spec, mandatory): this module owns a closed,
hardcoded allowlist mapping (workflow_key, version) -> one specific
API-format ComfyUI graph file. There is no "scan the workflows folder"
fallback and no way to resolve a graph by an arbitrary path — anything
else would let an untrusted JSON file (a frontend upload, LLM output, a
stray file someone drops in the folder) reach ComfyUI as if it were an
approved workflow. Every VisualAssetService caller (23D-I+) must go
through load_workflow_graph(); nothing else in this codebase should ever
open a workflow JSON file directly.

Each entry's produces_asset_type reuses app.game.visual.spec's own
FUTURE_ASSET_KINDS — the closed asset-type vocabulary Phase 21Q already
established — rather than inventing a second, parallel enum.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings
from app.game.visual.spec import FUTURE_ASSET_KINDS


class VisualWorkflowRegistryError(Exception):
    """Base for every workflow-registry failure."""


class WorkflowNotFoundError(VisualWorkflowRegistryError):
    """Raised when (key, version) — or a "current" lookup for key — is not
    in the registered allowlist."""


class WorkflowFileMissingError(VisualWorkflowRegistryError):
    """Raised when a registered entry's file is not actually on disk."""


@dataclass(frozen=True)
class WorkflowDefinition:
    key: str
    version: str
    produces_asset_type: str
    filename: str
    is_current: bool
    description: str

    def __post_init__(self) -> None:
        if self.produces_asset_type not in FUTURE_ASSET_KINDS:
            raise VisualWorkflowRegistryError(
                f"{self.key} {self.version} declares an unknown asset type: "
                f"{self.produces_asset_type!r}"
            )


# Phase 23B/23B.1/23B.2 — item V1/V2 were calibration iterations superseded
# by the approved EVERREACH_ITEM_STYLE_V3 baseline (APPROVED_MUNDANE_BASELINE).
# They stay registered (not deleted) so anything referencing them stays
# resolvable, but is_current=False keeps every new caller on V3 by default.
_WORKFLOWS: tuple[WorkflowDefinition, ...] = (
    WorkflowDefinition(
        key="EVERREACH_ITEM", version="V1", produces_asset_type="ITEM_ILLUSTRATION",
        filename="EVERREACH_ITEM_V1_API.json", is_current=False,
        description="Phase 23B — first item generation pass, superseded.",
    ),
    WorkflowDefinition(
        key="EVERREACH_ITEM", version="V2", produces_asset_type="ITEM_ILLUSTRATION",
        filename="EVERREACH_ITEM_V2_API.json", is_current=False,
        description="Phase 23B.1 — item style calibration pass, superseded.",
    ),
    WorkflowDefinition(
        key="EVERREACH_ITEM", version="V3", produces_asset_type="ITEM_ILLUSTRATION",
        filename="EVERREACH_ITEM_V3_API.json", is_current=True,
        description="Phase 23B final baseline — EVERREACH_ITEM_STYLE_V3 (APPROVED_MUNDANE_BASELINE).",
    ),
    WorkflowDefinition(
        key="EVERREACH_NPC_PORTRAIT", version="V1", produces_asset_type="NPC_PORTRAIT",
        filename="EVERREACH_NPC_PORTRAIT_V1_API.json", is_current=True,
        description="Phase 23C — text-to-image NPC canonical reference portrait.",
    ),
    WorkflowDefinition(
        key="EVERREACH_NPC_IDENTITY", version="V1", produces_asset_type="NPC_PORTRAIT",
        filename="EVERREACH_NPC_IDENTITY_V1_API.json", is_current=True,
        description="Phase 23C.1 — identity-preserving image-edit for NPC variant portraits.",
    ),
)


def _root(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    if not settings.comfyui_workflow_root:
        raise VisualWorkflowRegistryError("comfyui_workflow_root is not configured.")
    return Path(settings.comfyui_workflow_root)


def list_workflows() -> tuple[WorkflowDefinition, ...]:
    return _WORKFLOWS


def get_workflow_definition(key: str, version: str) -> WorkflowDefinition:
    for workflow in _WORKFLOWS:
        if workflow.key == key and workflow.version == version:
            return workflow
    raise WorkflowNotFoundError(f"No registered workflow {key!r} version {version!r}.")


def get_current_workflow_definition(key: str) -> WorkflowDefinition:
    for workflow in _WORKFLOWS:
        if workflow.key == key and workflow.is_current:
            return workflow
    raise WorkflowNotFoundError(f"No current workflow registered for key {key!r}.")


def load_workflow_graph(key: str, version: str, *, settings: Settings | None = None) -> dict:
    """Return the parsed ComfyUI API-format node graph for (key, version).
    This is the ONLY sanctioned way to obtain a graph to pass to
    ComfyUIClient.submit_workflow.

    Strips "_everreach_meta" — every one of these files carries that
    key as human-readable provenance (which phase/version, what
    changed, why), never a real node. ComfyUI's own /prompt endpoint
    treats every top-level key as a node id and rejects anything
    without a class_type, so a caller submitting this dict verbatim
    would get a 400 "missing_node_type" the moment a real server
    actually validated it — exactly what the calibration scripts under
    E:\\RPG\\Workflows\\api already do by hand (graph.pop("_everreach_meta",
    None)) before every submission; this makes that step impossible to
    forget by doing it once, here, for every caller."""
    definition = get_workflow_definition(key, version)
    path = _root(settings) / definition.filename
    if not path.is_file():
        raise WorkflowFileMissingError(f"Workflow file not found on disk: {path}")
    with path.open("r", encoding="utf-8") as handle:
        graph = json.load(handle)
    graph.pop("_everreach_meta", None)
    return graph
