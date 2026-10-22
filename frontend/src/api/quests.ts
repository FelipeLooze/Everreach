import { api } from "@/api/client";
import type { Quest } from "@/types/game";

export const getQuests = (campaignId: string, characterId: string) =>
  api.get<{ quests: Quest[] }>(`/campaigns/${campaignId}/quests?character_id=${characterId}`);

export const acceptQuest = (campaignId: string, characterId: string, questId: string) =>
  api.post<Quest>(`/campaigns/${campaignId}/quests/${questId}/accept?character_id=${characterId}`);

export const abandonQuest = (campaignId: string, characterId: string, questId: string) =>
  api.post<Quest>(`/campaigns/${campaignId}/quests/${questId}/abandon?character_id=${characterId}`);
