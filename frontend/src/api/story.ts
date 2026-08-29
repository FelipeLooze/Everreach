import { api } from "@/api/client";
import type { StoryLog, StoryRegenerationResponse } from "@/types/game";

export const getStoryLog = (campaignId: string, characterId: string) =>
  api.get<StoryLog>(`/campaigns/${campaignId}/story?character_id=${encodeURIComponent(characterId)}`);

export const regenerateLastNarrative = (
  campaignId: string,
  characterId: string,
  feedback: string,
) =>
  api.post<StoryRegenerationResponse>(
    `/campaigns/${campaignId}/story/regenerate?character_id=${encodeURIComponent(characterId)}`,
    { feedback },
  );
