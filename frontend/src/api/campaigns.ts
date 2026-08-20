import { api } from "@/api/client";
import type { Campaign, CampaignWithCharacters, Character, WorldStartResponse } from "@/types/game";

export const listCampaigns = () => api.get<CampaignWithCharacters[]>("/campaigns");

export const createCampaign = (name: string) => api.post<Campaign>("/campaigns", { name });

export type EarthProfession = "CHEF" | "FARMER" | "CARPENTER" | "BLACKSMITH";

export const createCharacter = (
  campaignId: string,
  name: string,
  earthProfession: EarthProfession | null,
) =>
  api.post<Character>(`/campaigns/${campaignId}/characters`, {
    name,
    earth_profession: earthProfession,
  });

export const startWorld = (campaignId: string, characterId: string) =>
  api.post<WorldStartResponse>(`/campaigns/${campaignId}/start?character_id=${encodeURIComponent(characterId)}`, {});

export const deleteCampaign = (campaignId: string) =>
  api.delete<{ deleted: boolean }>(`/campaigns/${campaignId}`);
