import { api } from "@/api/client";
import type { ActionResponse, ActionUndoResponse, ActionUndoStatus, GameState, PlantAction } from "@/types/game";

export const getState = (campaignId: string, characterId: string) =>
  api.get<GameState>(`/campaigns/${campaignId}/state?character_id=${characterId}`);

export const postAction = (
  campaignId: string,
  characterId: string,
  text: string,
  techniqueId?: string,
  plantAction?: PlantAction,
  formationAction?: { kind: "inspect" | "interact" },
) =>
  api.post<ActionResponse>(`/campaigns/${campaignId}/actions?character_id=${characterId}`, {
    text,
    action_key: crypto.randomUUID(),
    technique_id: techniqueId ?? null,
    plant_action: plantAction ?? null,
    formation_action: formationAction ?? null,
  });

export const getActionUndoStatus = (campaignId: string, characterId: string) =>
  api.get<ActionUndoStatus>(
    `/campaigns/${campaignId}/actions/undo-status?character_id=${encodeURIComponent(characterId)}`,
  );

export const undoLastAction = (
  campaignId: string,
  characterId: string,
  reason: string,
) =>
  api.post<ActionUndoResponse>(
    `/campaigns/${campaignId}/actions/undo-last?character_id=${encodeURIComponent(characterId)}`,
    { reason },
  );
