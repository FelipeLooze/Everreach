import { api } from "@/api/client";
import type { MapData, MapViewData } from "@/types/game";

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
