import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { GameSidebar } from "@/features/game/GameSidebar";
import type { GameState } from "@/types/game";

const state: GameState = {
  character: {
    id: "char_1", name: "Hero", background: null, profession_affinity_key: null,
    active_class_id: null, level: 2, xp: 0, hp_current: 20, hp_max: 20,
    mana_current: 10, mana_max: 10, stamina_current: 20, stamina_max: 20,
    status: "ALIVE", region_id: "region_1", location_id: "location_1",
  },
  region: { id: "region_1", name: "Vale", description: null, discovery_status: "DISCOVERED" },
  location: {
    id: "location_1", name: "Cardal", type: "village",
    description: "Uma vila de mercado.", discovery_status: "VISITED",
  },
  world_time: { year: 1, month: 2, day: 3, hour: 8, minute: 5 },
  nearby_npcs: [{ id: "npc_1", name: "Mara", role: "Ferreira" }],
  nearby_simulated_players: [{
    id: "simp_1", name: "Caio", level: 4, xp: 0, archetype: "EXPLORER",
    risk_tolerance: "BALANCED", goal: "", group_id: null,
  }],
  active_quests: [{ quest_id: "quest_1", name: "A estrada perdida", status: "ACTIVE" }],
  opening_narrative: null,
  opening_narrator_unavailable: false,
};

describe("GameSidebar", () => {
  afterEach(cleanup);

  it("mostra somente os dados canônicos disponíveis no GameState", () => {
    render(<GameSidebar state={state} />);

    expect(screen.getByText("Cardal")).toBeInTheDocument();
    expect(screen.getByText("Uma vila de mercado.")).toBeInTheDocument();
    expect(screen.getByText("Mara")).toBeInTheDocument();
    expect(screen.getByText("Caio")).toBeInTheDocument();
    expect(screen.getByText("08:05")).toBeInTheDocument();
    expect(screen.getByText("A estrada perdida")).toBeInTheDocument();
  });

  it("trata listas vazias sem inventar informações", () => {
    render(
      <GameSidebar
        state={{
          ...state,
          nearby_npcs: [],
          nearby_simulated_players: [],
          active_quests: [],
        }}
      />,
    );

    expect(screen.getByText("Ninguém por perto.")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma missão ativa.")).toBeInTheDocument();
  });
});
