export interface NarrativeEntry {
  id: string;
  kind: "player" | "narrator" | "system";
  text: string;
}

export function NarrativeLog({
  entries,
  pending = false,
}: {
  entries: NarrativeEntry[];
  pending?: boolean;
}) {
  return (
    <div className="narrative-log">
      {entries.length === 0 && !pending && <p className="narrative-empty">A história ainda não começou.</p>}
      {entries.map((entry) => (
        <p key={entry.id} className={`narrative-entry narrative-${entry.kind}`}>
          {entry.kind === "player" ? <strong>&gt; {entry.text}</strong> : entry.text}
        </p>
      ))}
      {pending && (
        <p className="narrative-entry narrative-thinking" role="status" aria-label="O narrador está respondendo">
          <span className="thinking-dot" />
          <span className="thinking-dot" />
          <span className="thinking-dot" />
        </p>
      )}
    </div>
  );
}
