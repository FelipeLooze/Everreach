import type { GameState } from "@/types/game";

function formatTime(state: GameState) {
  if (!state.world_time) return "--:--";
  return `${String(state.world_time.hour).padStart(2, "0")}:${String(
    state.world_time.minute,
  ).padStart(2, "0")}`;
}

export function GameSidebar({ state }: { state: GameState }) {
  const { location, nearby_npcs, nearby_simulated_players } = state;
  const activeQuest = state.active_quests[0] ?? null;

  return (
    <aside className="game-sidebar">
      <section className="sidebar-section sidebar-location">
        <div className="sidebar-heading">
          <span className="sidebar-heading-line" />
          <span>LOCAL ATUAL</span>
        </div>

        <h2>{location?.name ?? "Desconhecido"}</h2>
        <span className="location-type">{location?.type ?? "Local desconhecido"}</span>
        <p>{location?.description ?? "Você ainda não conhece este lugar."}</p>
      </section>

      <section className="sidebar-section">
        <div className="sidebar-heading">
          <span className="sidebar-heading-line" />
          <span>PESSOAS VISÍVEIS</span>
          <strong className="sidebar-count">
            {nearby_npcs.length + nearby_simulated_players.length}
          </strong>
        </div>

        <div className="people-list">
          {nearby_npcs.length === 0 && nearby_simulated_players.length === 0 && (
            <p className="sidebar-muted">Ninguém por perto.</p>
          )}

          {nearby_npcs.map((npc) => (
            <div className="person-row" key={npc.id}>
              <div className="person-name">
                <span className="presence-dot" />
                <span>{npc.name}</span>
              </div>
              <span className="person-role">{npc.role}</span>
            </div>
          ))}

          {nearby_simulated_players.map((player) => (
            <div className="person-row" key={player.id}>
              <div className="person-name">
                <span className="presence-dot player-dot" />
                <span>{player.name}</span>
              </div>
              <span className="person-role">Nível {player.level}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="sidebar-section">
        <div className="sidebar-heading">
          <span className="sidebar-heading-line" />
          <span>TEMPO</span>
        </div>

        <div className="world-time-card">
          <strong>{formatTime(state)}</strong>
          {state.world_time && (
            <span>
              Dia {state.world_time.day} / Mês {state.world_time.month} / {state.world_time.year}
            </span>
          )}
        </div>
      </section>

      <section className="sidebar-section sidebar-quest">
        <div className="sidebar-heading">
          <span className="sidebar-heading-line" />
          <span>QUEST ATUAL</span>
        </div>

        {activeQuest ? (
          <>
            <h3>{activeQuest.name}</h3>
            <p className="quest-state">{activeQuest.status}</p>
          </>
        ) : (
          <p className="sidebar-muted">Nenhuma missão ativa.</p>
        )}
      </section>
    </aside>
  );
}
