"""Phase 23D-N/23D-O — Visual Asset Service API.

"Frontend -> Backend -> VisualAssetService -> ComfyUIClient -> ComfyUI"
(spec, mandatory): this is the ONLY HTTP surface for visual generation
in the whole app. No route here accepts a raw prompt, a raw ComfyUI
graph, or ComfyUI's own address — a generation target is always
(entity_type, entity_id, asset_type); app.game.visual.entity_prompt is
the one place that turns that into an actual prompt, always derived
from already-established Canon (23D-G/21D/21E), never from caller text.

"COMFYUI FAILURE != GAMEPLAY FAILURE" (spec, mandatory) still holds at
this layer: a failed generation is a normal 200 response carrying a
FAILED VisualGenerationRequest, never a 5xx — only a genuinely bad
request (unknown campaign/entity, unsupported target, bad validation
status) is an HTTP error.

23D-O adds the one place a browser is ever handed image bytes:
GET .../{asset_id}/file streams the file this server resolves via
app.game.visual.asset_storage.resolve_asset_path — the frontend never
sees, and VisualAssetResponse never exposes, a raw storage_path.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies.comfyui import get_comfyui_client
from app.db.database import get_db
from app.db.models.campaign import Campaign
from app.db.models.visual_asset import VisualAsset
from app.db.models.visual_generation_request import VisualGenerationRequest
from app.game.visual.asset_storage import VisualAssetStorageError, resolve_asset_path
from app.game.visual.comfyui_client import ComfyUIClient
from app.game.visual.entity_prompt import (
    UnsupportedGenerationTargetError,
    resolve_generation_inputs,
)
from app.game.visual.item import ItemVisualIdentityError
from app.game.visual.npc import NPCVisualIdentityError
from app.game.visual.prompt_builder import VisualPromptBuilderError
from app.game.visual.retry_policy import RetryNotAllowedError, retry_visual_asset_request
from app.game.visual.service import request_visual_asset
from app.game.visual.validation import VisualAssetValidationError, set_validation_status
from app.game.visual.versioning import get_current_asset
from app.schemas.visual import (
    GenerateVisualAssetRequest,
    ValidationUpdateRequest,
    VisualAssetResponse,
    VisualGenerationRequestResponse,
)

router = APIRouter(prefix="/api/campaigns", tags=["visual-assets"])


def _require_campaign(db: Session, campaign_id: str) -> None:
    if db.get(Campaign, campaign_id) is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")


def _get_request_or_404(db: Session, campaign_id: str, request_id: str) -> VisualGenerationRequest:
    request = db.get(VisualGenerationRequest, request_id)
    if request is None or request.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Solicitação de geração não encontrada")
    return request


def _request_response(request: VisualGenerationRequest) -> VisualGenerationRequestResponse:
    return VisualGenerationRequestResponse(
        id=request.id,
        status=request.status,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        asset_type=request.asset_type,
        workflow_key=request.workflow_key,
        workflow_version=request.workflow_version,
        attempt_count=request.attempt_count,
        error_code=request.error_code,
        error_message=request.error_message,
        result_asset_id=request.result_asset_id,
    )


def _asset_response(campaign_id: str, asset: VisualAsset) -> VisualAssetResponse:
    return VisualAssetResponse(
        id=asset.id,
        entity_type=asset.entity_type,
        entity_id=asset.entity_id,
        asset_type=asset.asset_type,
        mime_type=asset.mime_type,
        width=asset.width,
        height=asset.height,
        validation_status=asset.validation_status,
        is_current=asset.is_current,
        is_canonical_reference=asset.is_canonical_reference,
        url=f"/api/campaigns/{campaign_id}/visual-assets/{asset.id}/file",
    )


@router.post("/{campaign_id}/visual-assets/generate", response_model=VisualGenerationRequestResponse)
def generate_visual_asset(
    campaign_id: str,
    body: GenerateVisualAssetRequest,
    db: Session = Depends(get_db),
    comfyui_client: ComfyUIClient = Depends(get_comfyui_client),
):
    _require_campaign(db, campaign_id)
    try:
        workflow_key, workflow_version, prompt_text, seed = resolve_generation_inputs(
            db, campaign_id, body.entity_type, body.entity_id, body.asset_type
        )
    except (UnsupportedGenerationTargetError, VisualPromptBuilderError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (NPCVisualIdentityError, ItemVisualIdentityError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    request = request_visual_asset(
        db,
        comfyui_client,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        asset_type=body.asset_type,
        workflow_key=workflow_key,
        workflow_version=workflow_version,
        prompt_text=prompt_text,
        seed=seed,
        campaign_id=campaign_id,
    )
    return _request_response(request)


@router.get(
    "/{campaign_id}/visual-assets/requests/{request_id}",
    response_model=VisualGenerationRequestResponse,
)
def get_visual_generation_request(campaign_id: str, request_id: str, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    request = _get_request_or_404(db, campaign_id, request_id)
    return _request_response(request)


@router.post(
    "/{campaign_id}/visual-assets/requests/{request_id}/retry",
    response_model=VisualGenerationRequestResponse,
)
def retry_visual_generation_request(
    campaign_id: str,
    request_id: str,
    db: Session = Depends(get_db),
    comfyui_client: ComfyUIClient = Depends(get_comfyui_client),
):
    _require_campaign(db, campaign_id)
    failed_request = _get_request_or_404(db, campaign_id, request_id)

    try:
        _workflow_key, _workflow_version, prompt_text, _seed = resolve_generation_inputs(
            db, campaign_id, failed_request.entity_type, failed_request.entity_id, failed_request.asset_type
        )
    except VisualPromptBuilderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (UnsupportedGenerationTargetError, NPCVisualIdentityError, ItemVisualIdentityError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        retried = retry_visual_asset_request(
            db, comfyui_client, failed_request.id, prompt_text=prompt_text,
        )
    except RetryNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return _request_response(retried)


@router.get("/{campaign_id}/visual-assets/current", response_model=VisualAssetResponse)
def get_current_visual_asset(
    campaign_id: str,
    entity_type: str,
    entity_id: str,
    asset_type: str,
    db: Session = Depends(get_db),
):
    _require_campaign(db, campaign_id)
    asset = get_current_asset(db, campaign_id, entity_type, entity_id, asset_type)
    if asset is None:
        raise HTTPException(status_code=404, detail="Nenhum asset visual atual para esta entidade")
    return _asset_response(campaign_id, asset)


@router.get("/{campaign_id}/visual-assets/{asset_id}/file")
def get_visual_asset_file(campaign_id: str, asset_id: str, db: Session = Depends(get_db)):
    """The only place a browser is ever handed image bytes for a
    VisualAsset (spec, 23D-O: "never a raw filesystem path to the
    browser"). Frontend code should always use VisualAssetResponse.url
    rather than constructing this path itself."""
    _require_campaign(db, campaign_id)
    asset = db.get(VisualAsset, asset_id)
    if asset is None or asset.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Asset visual não encontrado nesta campanha")

    try:
        file_path = resolve_asset_path(asset.storage_path)
    except VisualAssetStorageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo do asset visual não encontrado em disco")

    return FileResponse(file_path, media_type=asset.mime_type)


@router.post("/{campaign_id}/visual-assets/{asset_id}/validate", response_model=VisualAssetResponse)
def validate_visual_asset(
    campaign_id: str,
    asset_id: str,
    body: ValidationUpdateRequest,
    db: Session = Depends(get_db),
):
    _require_campaign(db, campaign_id)
    asset = db.get(VisualAsset, asset_id)
    if asset is None or asset.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Asset visual não encontrado nesta campanha")

    try:
        updated = set_validation_status(db, asset_id, body.status)
    except VisualAssetValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.commit()
    return _asset_response(campaign_id, updated)
