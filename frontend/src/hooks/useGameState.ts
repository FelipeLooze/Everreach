import { useCallback, useEffect, useState } from "react";
import { getState } from "@/api/actions";
import { startWorld } from "@/api/campaigns";
import { ApiError } from "@/api/client";
import { useGameStore } from "@/stores/useGameStore";

export function useGameState() {
  const { campaignId, characterId, state, setState, clearSession } = useGameStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!campaignId || !characterId) return;
    setLoading(true);
    setError(null);
    try {
      let fresh = await getState(campaignId, characterId);
      if (fresh.region && fresh.location && !fresh.opening_narrative) {
        const recoveredStart = await startWorld(campaignId, characterId);
        fresh = recoveredStart.state;
      }
      setState(fresh);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        clearSession();
        return;
      }
      setError(err instanceof Error ? err.message : "Falha ao carregar o estado do jogo.");
    } finally {
      setLoading(false);
    }
  }, [campaignId, characterId, setState, clearSession]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { state, loading, error, refresh };
}
