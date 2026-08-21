import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CombatPanel } from "@/features/combat/CombatPanel";
import type { CombatEncounterSummary } from "@/types/game";

const encounter: CombatEncounterSummary = {
  encounter_id: "combat_1",
  status: "ACTIVE",
  round_number: 2,
  participants: [
    {
      participant_id: "combatant_1",
      actor_type: "CHARACTER",
      actor_id: "char_1",
      name: "Hero",
      side_key: "player",
      range_band: "ENGAGED",
      hp_current: 18,
      hp_max: 20,
      is_current_turn: true,
    },
    {
      participant_id: "combatant_2",
      actor_type: "NPC",
      actor_id: "npc_1",
      name: "Bandido",
      side_key: "hostile",
      range_band: "ENGAGED",
      hp_current: 5,
      hp_max: 12,
      is_current_turn: false,
    },
  ],
};

describe("CombatPanel", () => {
  afterEach(cleanup);

  it("mostra que não há combate quando o encontro é nulo", () => {
    render(<CombatPanel encounter={null} />);

    expect(screen.getByText("Nenhum combate em andamento.")).toBeInTheDocument();
  });

  it("mostra rodada, status e HP de cada participante por lado", () => {
    render(<CombatPanel encounter={encounter} />);

    expect(screen.getByText("Rodada 2 — Em andamento")).toBeInTheDocument();
    expect(screen.getByText("Seu grupo")).toBeInTheDocument();
    expect(screen.getByText("Oponentes")).toBeInTheDocument();

    const heroCard = screen.getByText("Hero").closest(".combat-participant-card");
    expect(heroCard).toHaveTextContent("18/20");
    expect(heroCard).toHaveTextContent("corpo a corpo");
    expect(heroCard).toHaveTextContent("turno atual");
    expect(heroCard).toHaveClass("combat-participant-active");

    const banditCard = screen.getByText("Bandido").closest(".combat-participant-card");
    expect(banditCard).toHaveTextContent("5/12");
    expect(banditCard).toHaveTextContent("corpo a corpo");
    expect(banditCard).not.toHaveTextContent("turno atual");
    expect(banditCard).not.toHaveClass("combat-participant-active");
  });
});
