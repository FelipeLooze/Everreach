import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getCharacterSheet } from "@/api/character";
import { CharacterSheetPanel } from "@/features/character/CharacterSheetPanel";

vi.mock("@/api/character", () => ({
  getCharacterSheet: vi.fn(),
}));

describe("CharacterSheetPanel", () => {
  afterEach(() => {
    cleanup();
    vi.resetAllMocks();
  });

  it("mostra XP de personagem com uma casa decimal", async () => {
    vi.mocked(getCharacterSheet).mockResolvedValue({
      character: {
        id: "char_1",
        name: "Heroína",
        level: 0,
        xp: 12.5,
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
      attributes: [],
      skills: [],
      techniques: [],
    });

    render(
      <CharacterSheetPanel campaignId="campaign_1" characterId="char_1" />,
    );

    expect(await screen.findByText("XP: 12.5")).toBeInTheDocument();
  });
});
