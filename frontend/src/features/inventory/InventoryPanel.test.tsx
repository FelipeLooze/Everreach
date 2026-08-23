import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { InventoryPanel } from "@/features/inventory/InventoryPanel";

const mocks = vi.hoisted(() => ({
  getInventory: vi.fn(),
  getCurrentVisualAsset: vi.fn(),
}));

vi.mock("@/api/inventory", () => ({
  getInventory: mocks.getInventory,
}));

vi.mock("@/api/visual", () => ({
  getCurrentVisualAsset: mocks.getCurrentVisualAsset,
}));

describe("InventoryPanel", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getCurrentVisualAsset.mockRejectedValue(new ApiError(404, "not found"));
    mocks.getInventory.mockResolvedValue({
      items: [
        {
          item_instance_id: "instance_1",
          item_id: "item_1",
          name: "Rações",
          type: "CONSUMABLE",
          quantity: 3,
          quality: "STANDARD",
          condition: null,
          material: null,
          equipped: false,
          unit_weight: 1.5,
          total_weight: 4.5,
          equipped_slot: null,
          accessibility: "STOWED",
          allowed_slots: [],
          weapon: null,
          armor: null,
          tool: null,
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
    const card = (await screen.findByText("Rações")).closest(".inventory-item-card");
    expect(card).toHaveTextContent("4,5 de peso");
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
    expect(screen.getByText("Nada equipado.")).toBeInTheDocument();
    expect(screen.getByText("A mochila está vazia.")).toBeInTheDocument();
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
          quality: "GOOD",
          condition: "EXCELLENT",
          material: { key: "STEEL", name: "Aço" },
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
          armor: null,
          tool: null,
        },
      ],
      total_weight: 2,
      carrying_capacity: 25,
      load_ratio: 0.08,
      encumbrance: "NORMAL",
    });

    render(<InventoryPanel campaignId="campaign_1" characterId="char_1" />);

    const card = (await screen.findByText("Espada")).closest(".inventory-item-card");
    expect(card).toHaveTextContent("mão principal");
    expect(card).toHaveTextContent("uso imediato");
    expect(card).toHaveTextContent("espada · perfuração/corte · alcance normal · uma mão");
  });

  it("mostra cobertura e proteção física da armadura", async () => {
    mocks.getInventory.mockResolvedValue({
      items: [{
        item_instance_id: "instance_3", item_id: "item_3", name: "Gibão",
        type: "ARMOR", quantity: 1, equipped: true, unit_weight: 4,
        quality: "POOR",
        condition: "WORN",
        material: { key: "LEATHER", name: "Couro" },
        total_weight: 4, equipped_slot: "TORSO", accessibility: "WORN",
        allowed_slots: ["TORSO"], weapon: null,
        armor: {
          coverage: ["TORSO", "ARMS"],
          physical_protections: { SLASH: 3, PIERCE: 2, BLUNT: 1 },
        },
        tool: null,
      }],
      total_weight: 4, carrying_capacity: 25, load_ratio: 0.16, encumbrance: "NORMAL",
    });

    render(<InventoryPanel campaignId="campaign_1" characterId="char_1" />);
    const card = (await screen.findByText("Gibão")).closest(".inventory-item-card");
    expect(card).toHaveTextContent("cobre torso, braços");
    expect(card).toHaveTextContent("corte 3");
  });

  it("mostra as capacidades práticas de uma ferramenta", async () => {
    mocks.getInventory.mockResolvedValue({
      items: [{
        item_instance_id: "instance_4", item_id: "item_4", name: "Picareta",
        type: "TOOL", quantity: 1, equipped: false, unit_weight: 3,
        quality: "MASTERWORK",
        condition: "DAMAGED",
        material: { key: "IRON", name: "Ferro" },
        total_weight: 3, equipped_slot: null, accessibility: "STOWED",
        allowed_slots: ["MAIN_HAND", "BACK"], weapon: null, armor: null,
        tool: { capabilities: ["HAMMERING", "MINING"] },
      }],
      total_weight: 3, carrying_capacity: 25, load_ratio: 0.12, encumbrance: "NORMAL",
    });

    render(<InventoryPanel campaignId="campaign_1" characterId="char_1" />);
    const card = (await screen.findByText("Picareta")).closest(".inventory-item-card");
    expect(card).toHaveTextContent("ferramenta para martelar, minerar");
    expect(card).toHaveTextContent("qualidade obra-prima");
    expect(card).toHaveTextContent("material Ferro");
    expect(card?.querySelector(".state-badge-warning")).toHaveTextContent("danificada");
  });

  it("mostra a condição como um StateBadge com tom de acordo com a severidade", async () => {
    mocks.getInventory.mockResolvedValue({
      items: [{
        item_instance_id: "instance_5", item_id: "item_5", name: "Escudo Rachado",
        type: "ARMOR", quantity: 1, equipped: false, unit_weight: 3,
        quality: "STANDARD",
        condition: "BROKEN",
        material: null,
        total_weight: 3, equipped_slot: null, accessibility: "STOWED",
        allowed_slots: [], weapon: null, armor: null, tool: null,
      }],
      total_weight: 3, carrying_capacity: 25, load_ratio: 0.12, encumbrance: "NORMAL",
    });

    render(<InventoryPanel campaignId="campaign_1" characterId="char_1" />);
    const card = (await screen.findByText("Escudo Rachado")).closest(".inventory-item-card");

    expect(card?.querySelector(".state-badge-danger")).toHaveTextContent("quebrada");
  });

  it("mostra a nota de ornamentação de assinatura quando o item tem uma", async () => {
    mocks.getInventory.mockResolvedValue({
      items: [{
        item_instance_id: "instance_6", item_id: "item_6", name: "Lâmina do Lobo",
        type: "WEAPON", quantity: 1, equipped: false, unit_weight: 2,
        quality: "GOOD",
        condition: null,
        material: null,
        total_weight: 2, equipped_slot: null, accessibility: "STOWED",
        allowed_slots: [], weapon: null, armor: null, tool: null,
        signature_ornamentation: "punho em formato de cabeça de lobo",
      }],
      total_weight: 2, carrying_capacity: 25, load_ratio: 0.08, encumbrance: "NORMAL",
    });

    render(<InventoryPanel campaignId="campaign_1" characterId="char_1" />);

    expect(await screen.findByText("punho em formato de cabeça de lobo")).toBeInTheDocument();
  });
});
