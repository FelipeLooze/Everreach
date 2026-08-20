import { api } from "@/api/client";
import type { ActionResponse, GameState } from "@/types/game";

export const getState = (campaignId: string, characterId: string) =>
  api.get<GameState>(`/campaigns/${campaignId}/state?character_id=${characterId}`);

export const postAction = (
  campaignId: string,
  characterId: string,
  text: string,
  techniqueId?: string,
) =>
  api.post<ActionResponse>(`/campaigns/${campaignId}/actions?character_id=${characterId}`, {
    text,
    action_key: crypto.randomUUID(),
    technique_id: techniqueId ?? null,
  });
