import { api } from "@/api/client";
import type { StoryLog } from "@/types/game";

export const getStoryLog = (campaignId: string, characterId: string) =>
  api.get<StoryLog>(`/campaigns/${campaignId}/story?character_id=${encodeURIComponent(characterId)}`);
