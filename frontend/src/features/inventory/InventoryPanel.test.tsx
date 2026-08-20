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
          item_id: "item_1",
          name: "Rações",
          type: "CONSUMABLE",
          quantity: 3,
          equipped: false,
          unit_weight: 1.5,
          total_weight: 4.5,
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
});
