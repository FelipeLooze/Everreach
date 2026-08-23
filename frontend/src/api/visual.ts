import { api } from "@/api/client";
import type { VisualAsset, VisualGenerationRequest } from "@/types/game";

// Phase 23D-O — minimal fetch helper for the visual-assets API
// (app/api/routes/visual_assets.py), NOT a full gallery/viewer UI —
// that is deliberately out of scope for this subphase. Never build an
// asset's <img> src from anything other than VisualAsset.url.

export const getCurrentVisualAsset = (
  campaignId: string,
  entityType: string,
  entityId: string,
  assetType: string,
) =>
  api.get<VisualAsset>(
    `/campaigns/${campaignId}/visual-assets/current` +
      `?entity_type=${entityType}&entity_id=${entityId}&asset_type=${assetType}`,
  );

export const generateVisualAsset = (
  campaignId: string,
  entityType: string,
  entityId: string,
  assetType: string,
) =>
  api.post<VisualGenerationRequest>(`/campaigns/${campaignId}/visual-assets/generate`, {
    entity_type: entityType,
    entity_id: entityId,
    asset_type: assetType,
  });

export const getVisualGenerationRequest = (campaignId: string, requestId: string) =>
  api.get<VisualGenerationRequest>(`/campaigns/${campaignId}/visual-assets/requests/${requestId}`);

export const retryVisualGenerationRequest = (campaignId: string, requestId: string) =>
  api.post<VisualGenerationRequest>(
    `/campaigns/${campaignId}/visual-assets/requests/${requestId}/retry`,
  );

export const validateVisualAsset = (
  campaignId: string,
  assetId: string,
  status: "VALID" | "INVALID",
) =>
  api.post<VisualAsset>(`/campaigns/${campaignId}/visual-assets/${assetId}/validate`, { status });
