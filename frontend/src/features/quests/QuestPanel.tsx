import { useCallback, useEffect, useState } from "react";
import { abandonQuest, acceptQuest, getQuests } from "@/api/quests";
import type { Quest } from "@/types/game";
import { questStatusLabel } from "@/utils/labels";

const HISTORY_STATUSES = new Set(["COMPLETED", "FAILED", "CANCELLED", "EXPIRED", "RESOLVED_EXTERNALLY"]);

export function QuestPanel({ campaignId, characterId }: { campaignId: string; characterId: string }) {
  const [quests, setQuests] = useState<Quest[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingQuestId, setPendingQuestId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await getQuests(campaignId, characterId);
      setQuests(response.quests);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar as missões.");
    }
  }, [campaignId, characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const updateQuest = async (quest: Quest, action: "accept" | "abandon") => {
    setPendingQuestId(quest.quest_id);
    setError(null);
    try {
      if (action === "accept") {
        await acceptQuest(campaignId, characterId, quest.quest_id);
      } else {
        await abandonQuest(campaignId, characterId, quest.quest_id);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível atualizar a missão.");
    } finally {
      setPendingQuestId(null);
    }
  };

  if (!quests) return error ? <p className="panel-error">{error}</p> : <p>Carregando…</p>;
  if (quests.length === 0) return <p className="panel-empty">Nenhuma missão conhecida ainda.</p>;

  const available = quests.filter((quest) => quest.status === "AVAILABLE");
  const active = quests.filter((quest) => quest.status === "ACTIVE");
  const history = quests.filter((quest) => HISTORY_STATUSES.has(quest.status));

  const renderQuest = (quest: Quest) => (
    <article key={quest.quest_id} className="quest-entry">
      <h4>
        {quest.name} <span className="quest-status">[{questStatusLabel(quest.status)}]</span>
      </h4>
      <p>{quest.description}</p>
      {quest.schedule && <p className="quest-schedule">Quando: {quest.schedule}</p>}
      <ul>
        {quest.objectives.map((objective) => (
          <li key={objective.id} className={objective.completed ? "objective-done" : ""}>
            {objective.completed ? "✓" : "○"} {objective.description}
          </li>
        ))}
      </ul>
      {quest.status === "AVAILABLE" && (
        <button
          className="quest-action-button"
          disabled={pendingQuestId === quest.quest_id}
          onClick={() => void updateQuest(quest, "accept")}
        >
          {pendingQuestId === quest.quest_id ? "Aceitando…" : "Aceitar missão"}
        </button>
      )}
      {quest.status === "ACTIVE" && (
        <button
          className="quest-action-button quest-action-secondary"
          disabled={pendingQuestId === quest.quest_id}
          onClick={() => void updateQuest(quest, "abandon")}
        >
          {pendingQuestId === quest.quest_id ? "Abandonando…" : "Abandonar missão"}
        </button>
      )}
    </article>
  );

  return (
    <div className="quest-list">
      {error && <p className="panel-error">{error}</p>}
      {available.length > 0 && <section><h3>Disponíveis</h3>{available.map(renderQuest)}</section>}
      {active.length > 0 && <section><h3>Em andamento</h3>{active.map(renderQuest)}</section>}
      {history.length > 0 && <section><h3>Histórico</h3>{history.map(renderQuest)}</section>}
    </div>
  );
}
