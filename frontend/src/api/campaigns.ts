import { api } from "@/api/client";
import type { Campaign, CampaignWithCharacters, Character, WorldStartResponse } from "@/types/game";

export const listCampaigns = () => api.get<CampaignWithCharacters[]>("/campaigns");

export const createCampaign = (name: string) => api.post<Campaign>("/campaigns", { name });

export const createCharacter = (campaignId: string, name: string) =>
  api.post<Character>(`/campaigns/${campaignId}/characters`, { name });

export const startWorld = (campaignId: string, characterId: string) =>
  api.post<WorldStartResponse>(`/campaigns/${campaignId}/start?character_id=${encodeURIComponent(characterId)}`, {});

export const deleteCampaign = (campaignId: string) =>
  api.delete<{ deleted: boolean }>(`/campaigns/${campaignId}`);
