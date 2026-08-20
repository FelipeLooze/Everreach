import type { GameState } from "@/types/game";

function Stat({ label, current, max, className }: { label: string; current: number; max: number; className: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <div className="stat-bar">
        <div className={`stat-fill ${className}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="stat-value">
        {Math.round(current)}/{Math.round(max)}
      </span>
    </div>
  );
}

export function StatusBar({ state }: { state: GameState }) {
  const { character, world_time, location } = state;
  return (
    <div className="status-bar">
      <div className="status-identity">
        <span className="char-name">{character.name}</span>
        <span className="char-level">Nível {character.level}</span>
        {character.status === "INCAPACITATED" && (
          <span className="char-incapacitated">INCAPACITADO</span>
        )}
        {character.status === "DEAD" && <span className="char-dead">FALECIDO</span>}
      </div>
      <div className="status-stats">
        <Stat label="Vida" current={character.hp_current} max={character.hp_max} className="hp" />
        <Stat label="Mana" current={character.mana_current} max={character.mana_max} className="mp" />
        <Stat label="Fôlego" current={character.stamina_current} max={character.stamina_max} className="sp" />
      </div>
      <div className="status-context">
        {location && (
          <span>{location.name ?? "Local desconhecido"}</span>
        )}
        {world_time && (
          <span>
            Dia {world_time.day}, {String(world_time.hour).padStart(2, "0")}:{String(world_time.minute).padStart(2, "0")}
          </span>
        )}
      </div>
    </div>
  );
}
