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

function sideLabel(sideKey: string) {
  return sideKey.charAt(0).toUpperCase() + sideKey.slice(1);
}

export function CombatPanel({ encounter }: { encounter: CombatEncounterSummary | null }) {
  if (!encounter) {
    return <p className="panel-empty">Nenhum combate em andamento.</p>;
  }

  const sides = Array.from(new Set(encounter.participants.map((participant) => participant.side_key)));

  return (
    <>
      <p>
        Rodada {encounter.round_number} — {statusLabels[encounter.status]}
      </p>
      {sides.map((side) => (
        <div key={side} className="combat-side">
          <h4>{sideLabel(side)}</h4>
          <ul>
            {encounter.participants
              .filter((participant) => participant.side_key === side)
              .map((participant) => (
                <li
                  key={participant.participant_id}
                  className={participant.is_current_turn ? "combat-current-turn" : undefined}
                >
                  <strong>{participant.name}</strong>
                  {participant.is_current_turn && <span> — turno atual</span>}
                  <div>
                    {Math.round(participant.hp_current)}/{Math.round(participant.hp_max)} HP —{" "}
                    {rangeBandLabels[participant.range_band]}
                  </div>
                </li>
              ))}
          </ul>
        </div>
      ))}
    </>
  );
}
