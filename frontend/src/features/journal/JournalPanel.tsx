import { useEffect, useState } from "react";
import { getJournal } from "@/api/journal";
import type { Journal } from "@/types/game";
import { eventTypeLabel } from "@/utils/labels";

export function JournalPanel({ campaignId, characterId }: { campaignId: string; characterId: string }) {
  const [journal, setJournal] = useState<Journal | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJournal(campaignId, characterId)
      .then(setJournal)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar o diário."));
  }, [campaignId, characterId]);

  if (error) return <p className="panel-error">{error}</p>;
  if (!journal) return <p>Carregando…</p>;

  return (
    <div>
      <h4>Memórias</h4>
      {journal.memories.length === 0 ? (
        <p className="panel-empty">Nenhuma memória registrada ainda.</p>
      ) : (
        <ul>
          {journal.memories.map((m) => (
            <li key={m.id}>
              {m.summary_text} <small>(importância {m.importance})</small>
            </li>
          ))}
        </ul>
      )}

      <h4>Eventos Recentes</h4>
      <ul>
        {journal.events.map((e) => (
          <li key={e.id}>{eventTypeLabel(e.event_type)}</li>
        ))}
      </ul>
    </div>
  );
}
