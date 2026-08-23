import { api } from "@/api/client";
import type { MapData, MapViewAnnotation, MapViewData, RoutePlan } from "@/types/game";

export const getMap = (
  campaignId: string,
  characterId: string,
) =>
  api.get<MapData>(
    `/campaigns/${campaignId}/map?character_id=${encodeURIComponent(characterId)}`
  );

export const getMapView = (
  campaignId: string,
  characterId: string,
  scope?: string,
) => {
  const params = new URLSearchParams({ character_id: characterId });
  if (scope) {
    params.set("scope", scope);
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
