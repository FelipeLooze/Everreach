import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InventoryPanel } from "@/features/inventory/InventoryPanel";

const mocks = vi.hoisted(() => ({
  getInventory: vi.fn(),
}));

vi.mock("@/api/inventory", () => ({
  getInventory: mocks.getInventory,
}));

describe("InventoryPanel", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getInventory.mockResolvedValue({
      items: [
        {
          item_instance_id: "instance_1",
          item_id: "item_1",
          name: "Rações",
          type: "CONSUMABLE",
          quantity: 3,
          equipped: false,
          unit_weight: 1.5,
          total_weight: 4.5,
          equipped_slot: null,
          accessibility: "STOWED",
          allowed_slots: [],
          weapon: null,
        },
      ],
      total_weight: 4.5,
      carrying_capacity: 25,
      load_ratio: 0.18,
      encumbrance: "NORMAL",
    });
  });

  it("mostra peso, capacidade e estado de carga em português", async () => {
    render(<InventoryPanel campaignId="campaign_1" characterId="char_1" />);

    expect(await screen.findByText(/Peso: 4,5 \/ 25,0/)).toBeInTheDocument();
    expect(screen.getByText(/Carga normal/)).toBeInTheDocument();
    expect(screen.getByText(/Rações/)).toHaveTextContent("4,5 de peso");
  });

  it("continua mostrando a capacidade quando o inventário está vazio", async () => {
    mocks.getInventory.mockResolvedValue({
      items: [],
      total_weight: 0,
      carrying_capacity: 25,
      load_ratio: 0,
      encumbrance: "NORMAL",
    });

    render(<InventoryPanel campaignId="campaign_1" characterId="char_1" />);

    expect(await screen.findByText(/Peso: 0,0 \/ 25,0/)).toBeInTheDocument();
    expect(screen.getByText("O inventário está vazio.")).toBeInTheDocument();
  });

  it("traduz a posição e a acessibilidade do equipamento", async () => {
    mocks.getInventory.mockResolvedValue({
      items: [
        {
          item_instance_id: "instance_2",
          item_id: "item_2",
          name: "Espada",
          type: "WEAPON",
          quantity: 1,
          equipped: true,
          unit_weight: 2,
          total_weight: 2,
          equipped_slot: "MAIN_HAND",
          accessibility: "IMMEDIATE",
          allowed_slots: ["MAIN_HAND", "WAIST"],
          weapon: {
            family: "SWORD",
            damage_profiles: ["PIERCE", "SLASH"],
            reach: "NORMAL",
            hand_requirement: "ONE_HAND",
          },
        },
      ],
      total_weight: 2,
      carrying_capacity: 25,
      load_ratio: 0.08,
      encumbrance: "NORMAL",
    });

    render(<InventoryPanel campaignId="campaign_1" characterId="char_1" />);

    expect(await screen.findByText(/Espada/)).toHaveTextContent(
      "mão principal — uso imediato",
    );
    expect(screen.getByText(/Espada/)).toHaveTextContent(
      "espada; perfuração/corte; alcance normal; uma mão",
    );
  });
});
