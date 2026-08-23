from pydantic import BaseModel


class GenerateVisualAssetRequest(BaseModel):
    entity_type: str
    entity_id: str
    asset_type: str


class VisualGenerationRequestResponse(BaseModel):
    id: str
    status: str
    entity_type: str
    entity_id: str
    asset_type: str
    workflow_key: str
    workflow_version: str
    attempt_count: int
    error_code: str | None
    error_message: str | None
    result_asset_id: str | None


class VisualAssetResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    asset_type: str
    mime_type: str
    width: int
    height: int
    validation_status: str
    is_current: bool
    is_canonical_reference: bool
    # A backend-served URL (23D-O's file route) — never storage_path
    # itself, which is a server-internal filesystem detail this schema
    # deliberately never exposes.
    url: str


class ValidationUpdateRequest(BaseModel):
    status: str
