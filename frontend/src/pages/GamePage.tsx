import { Navigate } from "react-router-dom";
import { GameScreen } from "@/features/game/GameScreen";
import { useGameStore } from "@/stores/useGameStore";

export function GamePage() {
  const { campaignId, characterId } = useGameStore();

  if (!campaignId || !characterId) {
    return <Navigate to="/" replace />;
  }

  return <GameScreen />;
}
