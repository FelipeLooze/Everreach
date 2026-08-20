import { api } from "@/api/client";
import type {
  CharacterClassDefinition,
  CharacterClassOffer,
  CharacterSheet,
  SystemProgression,
} from "@/types/game";

export const getCharacterSheet = (campaignId: string, characterId: string) =>
  api.get<CharacterSheet>(`/campaigns/${campaignId}/character?character_id=${characterId}`);

export const getSystemProgression = (campaignId: string, characterId: string) =>
  api.get<SystemProgression>(
    `/campaigns/${campaignId}/character/progression?character_id=${characterId}`,
  );

export const acceptClassOffer = (
  campaignId: string,
  characterId: string,
  offerId: string,
) =>
  api.post<CharacterClassDefinition>(
    `/campaigns/${campaignId}/character/class-offers/${offerId}/accept?character_id=${encodeURIComponent(characterId)}`,
  );

export const delayClassOffer = (
  campaignId: string,
  characterId: string,
  offerId: string,
) =>
  api.post<CharacterClassOffer>(
    `/campaigns/${campaignId}/character/class-offers/${offerId}/delay?character_id=${encodeURIComponent(characterId)}`,
  );
