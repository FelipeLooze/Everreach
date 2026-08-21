import type { CombatEncounterSummary, CombatParticipantSummary } from "@/types/game";

const statusLabels: Record<CombatEncounterSummary["status"], string> = {
  ACTIVE: "Em andamento",
  VICTORY: "Vitória",
  DEFEAT: "Derrota",
  FLED: "Fuga",
  CANCELLED: "Encerrado",
};

const rangeBandLabels: Record<CombatParticipantSummary["range_band"], string> = {
  ENGAGED: "corpo a corpo",
  NEAR: "próximo",
  FAR: "distante",
  OUT_OF_REACH: "fora de alcance",
};

const sideLabels: Record<string, string> = {
  player: "Seu grupo",
  hostile: "Oponentes",
};

function sideLabel(sideKey: string) {
  return sideLabels[sideKey] ?? sideKey.charAt(0).toUpperCase() + sideKey.slice(1);
}

function ParticipantCard({ participant }: { participant: CombatParticipantSummary }) {
  const pct =
    participant.hp_max > 0
      ? Math.max(0, Math.min(100, (participant.hp_current / participant.hp_max) * 100))
      : 0;

  return (
    <article
      className={`fantasy-content-card combat-participant-card${
        participant.is_current_turn ? " combat-participant-active" : ""
      }`}
    >
      <div className="combat-participant-heading">
        <strong>{participant.name}</strong>
        {participant.is_current_turn && (
          <span className="inventory-tag combat-turn-tag">turno atual</span>
        )}
      </div>

      <div className="combat-hp-row">
        <div className="combat-hp-track">
          <div className="combat-hp-fill" style={{ width: `${pct}%` }} />
        </div>
        <span className="combat-hp-value">
          {Math.round(participant.hp_current)}/{Math.round(participant.hp_max)}
        </span>
      </div>

      <div className="inventory-item-tags">
        <span className="inventory-tag">{rangeBandLabels[participant.range_band]}</span>
      </div>
    </article>
  );
}

export function CombatPanel({ encounter }: { encounter: CombatEncounterSummary | null }) {
  if (!encounter) {
    return <p className="panel-empty">Nenhum combate em andamento.</p>;
  }

  const sides = Array.from(new Set(encounter.participants.map((participant) => participant.side_key)));

  return (
    <div className="inventory-panel">
      <p className="inventory-load-summary">
        Rodada {encounter.round_number} — {statusLabels[encounter.status]}
      </p>

      {sides.map((side) => (
        <section className="fantasy-section" key={side}>
          <h4 className="fantasy-section-title">{sideLabel(side)}</h4>
          <div className="inventory-item-grid">
            {encounter.participants
              .filter((participant) => participant.side_key === side)
              .map((participant) => (
                <ParticipantCard key={participant.participant_id} participant={participant} />
              ))}
          </div>
        </section>
      ))}
    </div>
  );
}
