import { api } from "@/api/client";
import type { Journal } from "@/types/game";

export const getJournal = (campaignId: string, characterId: string) =>
  api.get<Journal>(`/campaigns/${campaignId}/journal?character_id=${encodeURIComponent(characterId)}`);
