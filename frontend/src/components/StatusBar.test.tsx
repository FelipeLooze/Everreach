import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StatusBar } from "@/components/StatusBar";
import type { GameState } from "@/types/game";

const state: GameState = {
  character: {
    id: "char_1",
    name: "Hero",
    level: 0,
    xp: 0,
    hp_current: 20,
    hp_max: 20,
    mana_current: 10,
    mana_max: 10,
    stamina_current: 20,
    stamina_max: 20,
    status: "ALIVE",
    region_id: "region_1",
    location_id: "location_1",
  },
  region: {
    id: "region_1",
    name: null,
    description: null,
    discovery_status: "DISCOVERED",
  },
  location: {
    id: "location_1",
    name: null,
    type: "village",
    description: null,
    discovery_status: "VISITED",
  },
  world_time: {
    year: 1,
    month: 1,
    day: 1,
    hour: 8,
    minute: 0,
  },
  nearby_npcs: [],
  nearby_simulated_players: [],
  active_quests: [],
  opening_narrative: null,
  opening_narrator_unavailable: false,
};

describe("StatusBar", () => {
  afterEach(cleanup);

  it("mostra local desconhecido quando o nome canônico não é conhecido", () => {
    render(<StatusBar state={state} />);

    expect(
      screen.getByText("Local desconhecido")
    ).toBeInTheDocument();

    expect(screen.queryByText("Cardal")).not.toBeInTheDocument();
  });
});