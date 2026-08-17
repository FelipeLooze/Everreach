import { useEffect, useState } from "react";
import { getQuests } from "@/api/quests";
import type { Quest } from "@/types/game";
import { questStatusLabel } from "@/utils/labels";

export function QuestPanel({ campaignId, characterId }: { campaignId: string; characterId: string }) {
  const [quests, setQuests] = useState<Quest[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getQuests(campaignId, characterId)
      .then((res) => setQuests(res.quests))
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar as missões."));
  }, [campaignId, characterId]);

  if (error) return <p className="panel-error">{error}</p>;
  if (!quests) return <p>Carregando…</p>;
  if (quests.length === 0) return <p className="panel-empty">Nenhuma missão conhecida ainda.</p>;

  return (
    <div>
      {quests.map((quest) => (
        <div key={quest.quest_id} className="quest-entry">
          <h4>
            {quest.name} <span className="quest-status">[{questStatusLabel(quest.status)}]</span>
          </h4>
          <p>{quest.description}</p>
          <ul>
            {quest.objectives.map((obj) => (
              <li key={obj.id} className={obj.completed ? "objective-done" : ""}>
                {obj.completed ? "✓" : "○"} {obj.description}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
