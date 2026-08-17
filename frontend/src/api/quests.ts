import { api } from "@/api/client";
import type { Quest } from "@/types/game";

export const getQuests = (campaignId: string, characterId: string) =>
  api.get<{ quests: Quest[] }>(`/campaigns/${campaignId}/quests?character_id=${characterId}`);
