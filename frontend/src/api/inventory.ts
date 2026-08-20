import { api } from "@/api/client";
import type { Inventory } from "@/types/game";

export const getInventory = (campaignId: string, characterId: string) =>
  api.get<Inventory>(`/campaigns/${campaignId}/inventory?character_id=${characterId}`);
