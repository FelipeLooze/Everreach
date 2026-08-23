import { api } from "@/api/client";
import type { MapData, MapViewAnnotation, MapViewData, RoutePlan } from "@/types/game";

export const getMap = (
  campaignId: string,
  characterId: string,
) =>
  api.get<MapData>(
    `/campaigns/${campaignId}/map?character_id=${encodeURIComponent(characterId)}`
  );

// Phase 20O — detailLevel/viewport are optional server-side LOD
// filters (app.game.map.view). Not yet wired to live pan/zoom in the
// UI — the current game world is far from the scale where that
// matters; the capability exists and is tested, ready for whenever it
// does (see the Phase 20O report for this deferral's rationale).
export const getMapView = (
  campaignId: string,
  characterId: string,
  scope?: string,
  detailLevel?: string,
  viewport?: { minX: number; minY: number; maxX: number; maxY: number },
) => {
  const params = new URLSearchParams({ character_id: characterId });
  if (scope) {
    params.set("scope", scope);
  }
  if (detailLevel) {
    params.set("detail_level", detailLevel);
  }
  if (viewport) {
    params.set("min_x", String(viewport.minX));
    params.set("min_y", String(viewport.minY));
    params.set("max_x", String(viewport.maxX));
    params.set("max_y", String(viewport.maxY));
  }
  return api.get<MapViewData>(
    `/campaigns/${campaignId}/map-view?${params.toString()}`
  );
};

export const createMapAnnotation = (
  campaignId: string,
  characterId: string,
  locationId: string,
  text: string,
) =>
  api.post<MapViewAnnotation>(`/campaigns/${campaignId}/map-annotations`, {
    character_id: characterId,
    location_id: locationId,
    text,
  });

export const deleteMapAnnotation = (
  campaignId: string,
  characterId: string,
  annotationId: string,
) =>
  api.delete<{ deleted: boolean }>(
    `/campaigns/${campaignId}/map-annotations/${annotationId}?character_id=${encodeURIComponent(characterId)}`,
  );

export const getRoutePlan = (
  campaignId: string,
  characterId: string,
  fromLocationId: string,
  toLocationId: string,
) => {
  const params = new URLSearchParams({
    character_id: characterId,
    from_location_id: fromLocationId,
    to_location_id: toLocationId,
  });
  return api.get<RoutePlan>(`/campaigns/${campaignId}/route-plan?${params.toString()}`);
};
