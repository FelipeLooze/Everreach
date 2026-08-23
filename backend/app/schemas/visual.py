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
    # No servable URL yet — 23D-O adds the frontend-safe file endpoint;
    # until then, storage_path is a server-internal detail this schema
    # deliberately does not expose.


class ValidationUpdateRequest(BaseModel):
    status: str
