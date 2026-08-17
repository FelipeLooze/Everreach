import { api } from "@/api/client";
import type { MapData } from "@/types/game";

export const getMap = (campaignId: string) => api.get<MapData>(`/campaigns/${campaignId}/map`);
