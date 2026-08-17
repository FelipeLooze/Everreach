import { create } from "zustand";
import type { GameState } from "@/types/game";

interface GameStore {
  campaignId: string | null;
  characterId: string | null;
  state: GameState | null;
  setSession: (campaignId: string, characterId: string) => void;
  setState: (state: GameState) => void;
  clearSession: () => void;
}

const STORAGE_KEY = "vrmmo-session";

function loadSession(): { campaignId: string | null; characterId: string | null } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { campaignId: null, characterId: null };
    return JSON.parse(raw);
  } catch {
    return { campaignId: null, characterId: null };
  }
}

export const useGameStore = create<GameStore>((set) => ({
  ...loadSession(),
  state: null,
  setSession: (campaignId, characterId) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ campaignId, characterId }));
    set({ campaignId, characterId });
  },
  setState: (state) => set({ state }),
  clearSession: () => {
    localStorage.removeItem(STORAGE_KEY);
    set({ campaignId: null, characterId: null, state: null });
  },
}));
