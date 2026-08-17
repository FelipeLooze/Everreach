import { api } from "@/api/client";
import type { CharacterSheet } from "@/types/game";

export const getCharacterSheet = (campaignId: string, characterId: string) =>
  api.get<CharacterSheet>(`/campaigns/${campaignId}/character?character_id=${characterId}`);
