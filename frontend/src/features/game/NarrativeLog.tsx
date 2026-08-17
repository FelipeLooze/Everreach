export interface NarrativeEntry {
  id: string;
  kind: "player" | "narrator" | "system";
  text: string;
}

export function NarrativeLog({ entries }: { entries: NarrativeEntry[] }) {
  return (
    <div className="narrative-log">
      {entries.length === 0 && <p className="narrative-empty">A história ainda não começou.</p>}
      {entries.map((entry) => (
        <p key={entry.id} className={`narrative-entry narrative-${entry.kind}`}>
          {entry.kind === "player" ? <strong>&gt; {entry.text}</strong> : entry.text}
        </p>
      ))}
    </div>
  );
}
