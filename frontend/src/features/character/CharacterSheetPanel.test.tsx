import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  acceptClassOffer,
  delayClassOffer,
  getCharacterSheet,
} from "@/api/character";
import { CharacterSheetPanel } from "@/features/character/CharacterSheetPanel";

vi.mock("@/api/character", () => ({
  getCharacterSheet: vi.fn(),
  acceptClassOffer: vi.fn(),
  delayClassOffer: vi.fn(),
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
        background: null,
        profession_affinity_key: null,
        active_class_id: null,
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
      professions: [],
      active_class: null,
      class_offers: [],
      skills: [],
      techniques: [],
    });

    render(
      <CharacterSheetPanel campaignId="campaign_1" characterId="char_1" />,
    );

    expect(await screen.findByText("XP: 12.5")).toBeInTheDocument();
    expect(
      screen.getByText("Nenhuma profissão desenvolvida ainda."),
    ).toBeInTheDocument();
    expect(screen.getByText("Nenhuma classe ativa.")).toBeInTheDocument();
  });

  it("mostra somente profissões realmente iniciadas", async () => {
    vi.mocked(getCharacterSheet).mockResolvedValue({
      character: {
        id: "char_1",
        name: "Heroína",
        background: "Chef profissional na Terra",
        profession_affinity_key: "CULINARY",
        active_class_id: null,
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
      attributes: [],
      professions: [
        { key: "HERBALISM", name: "Herbalismo", level: 0, xp: 0.11 },
      ],
      active_class: null,
      class_offers: [],
      skills: [],
      techniques: [],
    });

    render(
      <CharacterSheetPanel campaignId="campaign_1" characterId="char_1" />,
    );

    expect(
      await screen.findByText("Herbalismo: Level 0 — 0.1 XP"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Experiência na Terra: Chef profissional na Terra"),
    ).toBeInTheDocument();
  });

  it("permite adiar uma oferta sem removê-la permanentemente", async () => {
    const availableSheet = {
      character: {
        id: "char_1",
        name: "Heroína",
        level: 0,
        xp: 0,
        background: null,
        profession_affinity_key: null,
        active_class_id: null,
        hp_current: 20,
        hp_max: 20,
        mana_current: 10,
        mana_max: 10,
        stamina_current: 20,
        stamina_max: 20,
        status: "ALIVE" as const,
        region_id: "region_1",
        location_id: "location_1",
      },
      attributes: [],
      professions: [],
      active_class: null,
      class_offers: [
        {
          id: "offer_1",
          status: "AVAILABLE" as const,
          class_definition: {
            id: "class_1",
            name: "Espadachim do Vento",
            description: "Integra esgrima, vento e mobilidade.",
          },
        },
      ],
      skills: [],
      techniques: [],
    };
    vi.mocked(getCharacterSheet)
      .mockResolvedValueOnce(availableSheet)
      .mockResolvedValueOnce({
        ...availableSheet,
        class_offers: [
          { ...availableSheet.class_offers[0], status: "DELAYED" as const },
        ],
      });
    vi.mocked(delayClassOffer).mockResolvedValue({
      ...availableSheet.class_offers[0],
      status: "DELAYED",
    });

    render(
      <CharacterSheetPanel campaignId="campaign_1" characterId="char_1" />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "ADIAR" }));

    await waitFor(() =>
      expect(delayClassOffer).toHaveBeenCalledWith(
        "campaign_1",
        "char_1",
        "offer_1",
      ),
    );
    expect(await screen.findByText("Oferta adiada.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ACEITAR" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "ADIAR" })).not.toBeInTheDocument();
    expect(acceptClassOffer).not.toHaveBeenCalled();
  });
});
