import { api } from "@/api/client";
import type { SocialState } from "@/types/game";

export const getSocialState = (campaignId: string, characterId: string) =>
  api.get<SocialState>(`/campaigns/${campaignId}/social?character_id=${characterId}`);
