import { useEffect, useState } from "react";
import { getJournal } from "@/api/journal";
import type { Journal } from "@/types/game";
import { eventTypeLabel } from "@/utils/labels";

function formatRecordedDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}

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
    <div className="journal-grimoire">
      <section className="fantasy-section">
        <h4 className="fantasy-section-title">Memórias</h4>
        {journal.memories.length === 0 ? (
          <p className="panel-empty">Nenhuma memória registrada ainda.</p>
        ) : (
          <div className="memory-grid">
            {journal.memories.map((memory) => (
              <article className="memory-card" key={memory.id}>
                <div className="memory-card-meta">
                  <span className="importance-badge">IMPORTÂNCIA {memory.importance}</span>
                  <time dateTime={memory.created_at}>{formatRecordedDate(memory.created_at)}</time>
                </div>
                <p>{memory.summary_text}</p>
              </article>
            ))}
          </div>
        )}
      </section>

      <div className="fantasy-divider" aria-hidden="true"><span /></div>

      <section className="fantasy-section">
        <h4 className="fantasy-section-title">Eventos Recentes</h4>
        {journal.events.length === 0 ? (
          <p className="panel-empty">Nenhum evento registrado ainda.</p>
        ) : (
          <div className="event-timeline">
            {journal.events.map((event) => (
              <article className="timeline-event" key={event.id}>
                <span className="timeline-marker" aria-hidden="true" />
                <div className="timeline-event-copy">
                  <strong>{eventTypeLabel(event.event_type)}</strong>
                  <time dateTime={event.created_at}>{formatRecordedDate(event.created_at)}</time>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
