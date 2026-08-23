"""Phase 23D-I — Generation Orchestration.

request_visual_asset is the ONLY place in this codebase that ties the
whole pipeline together: workflow_registry (23D-C) -> prompt injection
(23D-G) -> comfyui_client (23D-B) -> asset_storage (23D-F) ->
generation_request/VisualAsset persistence (23D-D/23D-E). No other
caller should orchestrate these pieces itself.

"DO NOT keep a database transaction open while waiting for ComfyUI"
(spec, mandatory): this function commits the PENDING request row,
releasing the transaction, before making the (possibly minutes-long —
see comfyui_generation_timeout_seconds) blocking call to ComfyUI, and
only opens a new transaction afterward to persist the COMPLETED/FAILED
result. A single direct in-process call — no queue, no worker pool, no
distributed infra (spec, mandatory: single-user architecture).

"COMFYUI FAILURE != GAMEPLAY FAILURE" (spec, mandatory): every failure
this function can hit while actually attempting generation — offline,
unreachable, rejected workflow, timeout, missing/invalid output, a
copy failure — is caught, classified into one of app.core.enums.
VisualGenerationErrorCode's closed categories (23D-J), and turned into
a FAILED VisualGenerationRequest row, never a raised exception. The
exception is caller programming errors (an unregistered workflow_key/
version) — those are raised immediately, before any request row is
even created, since no attempt was actually made. See
app.game.visual.retry_policy for the bounded automatic retry built on
top of this classification.

Before any of that, two dedup checks (23D-K) short-circuit the whole
pipeline: an already in-flight request for the same entity/asset_type
is returned as-is (no duplicate GPU work from a player reopening a UI
panel), and a fingerprint match against the current asset skips
ComfyUI entirely, completing the new request against the EXISTING
asset instead of generating a new one.
"""
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import VisualGenerationErrorCode
from app.core.ids import generate_id
from app.core.logging import get_logger
from app.db.models.visual_asset import VisualAsset
from app.db.models.visual_generation_request import VisualGenerationRequest
from app.game.visual.asset_storage import VisualAssetStorageError, persist_generated_asset
from app.game.visual.comfyui_client import ComfyUIClient, ComfyUIClientError
from app.game.visual.dedup import compute_spec_fingerprint, find_in_flight_request, find_reusable_asset
from app.game.visual.generation_request import create_request, mark_completed, mark_failed, mark_in_progress
from app.game.visual.prompt_builder import (
    VisualPromptBuilderError,
    extract_model_identifier,
    inject_workflow_parameters,
)
from app.game.visual.workflow_registry import (
    VisualWorkflowRegistryError,
    get_workflow_definition,
    load_workflow_graph,
)

from PIL import Image, UnidentifiedImageError

logger = get_logger("visual")


def _classify_comfyui_error(exc: ComfyUIClientError) -> str:
    message = str(exc).lower()
    if "disabled" in message or "could not reach" in message:
        return VisualGenerationErrorCode.COMFYUI_OFFLINE
    if "took too long" in message:
        return VisualGenerationErrorCode.GENERATION_TIMEOUT
    if "rejected" in message:
        # A ComfyUI node-validation rejection whose message names a
        # model file it could not load (e.g. "Value not in list" for a
        # UNETLoader/CheckpointLoader input) is a missing-model problem,
        # not an ordinary graph rejection — distinguishing the two saves
        # a human from re-reading ComfyUI's own console output to figure
        # out which one just happened.
        if "not in list" in message or "does not exist" in message or ".safetensors" in message:
            return VisualGenerationErrorCode.MODEL_MISSING
        return VisualGenerationErrorCode.COMFYUI_REJECTED_WORKFLOW
    return VisualGenerationErrorCode.UNKNOWN_ERROR


def _first_output_image(history_entry: dict) -> dict | None:
    for node_output in history_entry.get("outputs", {}).values():
        images = node_output.get("images")
        if images:
            return images[0]
    return None


def _fail(db: Session, request_id: str, error_code: str, error_message: str) -> VisualGenerationRequest:
    logger.warning(
        "Visual generation request %s failed: %s - %s", request_id, error_code, error_message
    )
    request = mark_failed(db, request_id, error_code, error_message)
    db.commit()
    return request


def request_visual_asset(
    db: Session,
    comfyui_client: ComfyUIClient,
    *,
    entity_type: str,
    entity_id: str,
    asset_type: str,
    workflow_key: str,
    workflow_version: str,
    prompt_text: str,
    seed: int,
    campaign_id: str | None = None,
    reference_image: str | None = None,
    settings: Settings | None = None,
    attempt_count: int = 1,
) -> VisualGenerationRequest:
    # Caller programming error: fail loudly BEFORE creating any request
    # row, since no attempt is actually being made.
    get_workflow_definition(workflow_key, workflow_version)

    in_flight = find_in_flight_request(db, campaign_id, entity_type, entity_id, asset_type)
    if in_flight is not None:
        return in_flight

    spec_fingerprint = compute_spec_fingerprint(
        prompt_text=prompt_text,
        workflow_key=workflow_key,
        workflow_version=workflow_version,
        seed=seed,
        reference_image=reference_image,
    )

    request = create_request(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        asset_type=asset_type,
        workflow_key=workflow_key,
        workflow_version=workflow_version,
        campaign_id=campaign_id,
        seed=seed,
        attempt_count=attempt_count,
    )
    db.commit()

    reusable_asset = find_reusable_asset(
        db, campaign_id, entity_type, entity_id, asset_type, spec_fingerprint
    )
    if reusable_asset is not None:
        completed_request = mark_completed(db, request.id, reusable_asset.id)
        db.commit()
        return completed_request

    if not comfyui_client.is_available():
        return _fail(
            db, request.id, VisualGenerationErrorCode.COMFYUI_OFFLINE,
            "ComfyUI is disabled or unreachable.",
        )

    mark_in_progress(db, request.id)
    db.commit()

    try:
        graph = load_workflow_graph(workflow_key, workflow_version, settings=settings)
    except VisualWorkflowRegistryError as exc:
        return _fail(db, request.id, VisualGenerationErrorCode.WORKFLOW_NOT_FOUND, str(exc))

    filename_prefix = f"everreach/{entity_type}/{entity_id}/{asset_type}/{request.id}"
    try:
        graph = inject_workflow_parameters(
            graph,
            prompt_text=prompt_text,
            seed=seed,
            filename_prefix=filename_prefix,
            reference_image=reference_image,
        )
    except VisualPromptBuilderError as exc:
        return _fail(db, request.id, VisualGenerationErrorCode.UNKNOWN_ERROR, str(exc))

    model_identifier = extract_model_identifier(graph) or "unknown"

    try:
        prompt_id = comfyui_client.submit_workflow(graph, client_id=request.id)
        history_entry = comfyui_client.wait_for_completion(prompt_id)
    except ComfyUIClientError as exc:
        return _fail(db, request.id, _classify_comfyui_error(exc), str(exc))

    image_ref = _first_output_image(history_entry)
    if image_ref is None:
        return _fail(
            db, request.id, VisualGenerationErrorCode.OUTPUT_NOT_FOUND,
            "ComfyUI history had no output image.",
        )

    try:
        raw_path = comfyui_client.resolve_output_path(image_ref["subfolder"], image_ref["filename"])
    except ComfyUIClientError as exc:
        return _fail(db, request.id, VisualGenerationErrorCode.OUTPUT_NOT_FOUND, str(exc))

    asset_id = generate_id("vasset")
    try:
        storage_path = persist_generated_asset(
            raw_path,
            campaign_id=campaign_id,
            entity_type=entity_type,
            entity_id=entity_id,
            asset_type=asset_type,
            asset_id=asset_id,
            settings=settings,
        )
    except VisualAssetStorageError as exc:
        return _fail(db, request.id, VisualGenerationErrorCode.FILE_COPY_FAILED, str(exc))

    try:
        with Image.open(raw_path) as image:
            width, height = image.size
            mime_type = f"image/{image.format.lower()}" if image.format else "application/octet-stream"
    except (UnidentifiedImageError, OSError) as exc:
        return _fail(
            db, request.id, VisualGenerationErrorCode.INVALID_OUTPUT,
            f"Could not read generated image: {exc}",
        )

    asset = VisualAsset(
        id=asset_id,
        campaign_id=campaign_id,
        entity_type=entity_type,
        entity_id=entity_id,
        asset_type=asset_type,
        storage_path=storage_path,
        mime_type=mime_type,
        width=width,
        height=height,
        workflow_key=workflow_key,
        workflow_version=workflow_version,
        model_identifier=model_identifier,
        seed=seed,
        spec_fingerprint=spec_fingerprint,
    )
    db.add(asset)
    db.flush()

    completed_request = mark_completed(db, request.id, asset.id)
    db.commit()
    return completed_request
