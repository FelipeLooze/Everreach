import { NarrativeLog } from "@/features/game/NarrativeLog";
import type { StoryEntry } from "@/types/game";

export function StoryLogPanel({ entries, error }: { entries: StoryEntry[]; error: string | null }) {
  if (error) return <p className="panel-error">{error}</p>;
  if (entries.length === 0) return <p className="panel-empty">Nenhuma mensagem registrada ainda.</p>;

  return <NarrativeLog entries={entries} />;
}
