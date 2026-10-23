import { api } from "@/api/client";
import type { EconomyState } from "@/types/game";

export const getEconomy = (campaignId: string, characterId: string) =>
  api.get<EconomyState>(`/campaigns/${campaignId}/economy?character_id=${characterId}`);
