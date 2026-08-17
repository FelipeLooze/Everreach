import { api } from "@/api/client";
import type { InventoryItem } from "@/types/game";

export const getInventory = (campaignId: string, characterId: string) =>
  api.get<{ items: InventoryItem[] }>(`/campaigns/${campaignId}/inventory?character_id=${characterId}`);
