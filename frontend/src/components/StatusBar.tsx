import type { GameState } from "@/types/game";

function Stat({ label, current, max, className }: { label: string; current: number; max: number; className: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;

  return (
    <div className="game-stat">
      <span className="game-stat-label">{label}</span>
      <div className="game-stat-track">
        <div className={`game-stat-fill ${className}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="game-stat-value">
        {Math.round(current)}/{Math.round(max)}
      </span>
    </div>
  );
}

export function StatusBar({ state }: { state: GameState }) {
  const { character, world_time, location, region } = state;
  const time = world_time
    ? `${String(world_time.hour).padStart(2, "0")}:${String(world_time.minute).padStart(2, "0")}`
    : "--:--";

  return (
    <header className="status-bar">
      <div className="everreach-brand">
        <div className="everreach-mark"><span>ER</span></div>
        <span className="everreach-title">EVERREACH</span>
      </div>

      <div className="status-character">
        <div className="level-shield"><strong>{character.level}</strong></div>
        <div className="character-identity">
          <strong>{character.name}</strong>
          <span>NÍVEL {character.level}</span>
        </div>
        {character.status === "INCAPACITATED" && (
          <span className="char-incapacitated">INCAPACITADO</span>
        )}
        {character.status === "DEAD" && <span className="char-dead">FALECIDO</span>}
      </div>

      <div className="status-stats">
        <Stat label="HP" current={character.hp_current} max={character.hp_max} className="hp" />
        <Stat label="MP" current={character.mana_current} max={character.mana_max} className="mp" />
        <Stat label="VIGOR" current={character.stamina_current} max={character.stamina_max} className="sp" />
      </div>

      <div className="status-world">
        <div className="world-info"><span>LOCAL</span><strong>{location?.name ?? "Desconhecido"}</strong></div>
        <div className="status-divider" />
        <div className="world-info"><span>REGIÃO</span><strong>{region?.name ?? "Desconhecida"}</strong></div>
        <div className="status-divider" />
        <div className="world-clock"><strong>{time}</strong></div>
      </div>
    </header>
  );
}
