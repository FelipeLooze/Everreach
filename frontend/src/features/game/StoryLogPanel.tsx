import type { StoryEntry } from "@/types/game";

export function StoryLogPanel({ entries, error }: { entries: StoryEntry[]; error: string | null }) {
  if (error) return <p className="panel-error">{error}</p>;
  if (entries.length === 0) return <p className="panel-empty">Nenhuma mensagem registrada ainda.</p>;

  return (
    <div className="story-register">
      {entries.map((entry, index) => (
        <div key={entry.id}>
          {index > 0 && <div className="fantasy-divider story-divider" aria-hidden="true"><span /></div>}
          <article className={`story-register-entry story-register-${entry.kind}`}>
            {entry.kind === "player" ? <strong>&gt; {entry.text}</strong> : <p>{entry.text}</p>}
          </article>
        </div>
      ))}
    </div>
  );
}
