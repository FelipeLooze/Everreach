import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EconomyPanel } from "@/features/economy/EconomyPanel";

const mocks = vi.hoisted(() => ({ getEconomy: vi.fn() }));
vi.mock("@/api/economy", () => mocks);

const economy = {
  balance_bronze: 24,
  location_name: "Ferraria de Cardal",
  shops: [{
    shop_id: "shop_1",
    name: "Ferraria de Mira",
    operator_available: true,
    listings: [{ listing_id: "listing_1", name: "Faca de Ferro", type: "WEAPON", quantity: 2, unit_price_bronze: 18 }],
    sellable_items: [],
  }],
  jobs: [{
    job_id: "job_1",
    title: "Ajudante de Ferreiro",
    description: "Auxiliar na forja.",
    employer_name: "Ferraria de Mira",
    wage_bronze: 12,
    payment_frequency: "PER_TASK",
    work_minutes: 180,
    schedule: "das 8h às 18h",
    application_status: "ACTIVE",
    employer_available: true,
  }],
  recipes: [],
};

describe("EconomyPanel", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getEconomy.mockResolvedValue(economy);
  });

  it("shows finite local stock, balance and jobs", async () => {
    render(<EconomyPanel campaignId="campaign_1" characterId="character_1" onAction={vi.fn()} />);

    expect(await screen.findByText("24 Bronze")).toBeInTheDocument();
    expect(screen.getByText("2 em estoque")).toBeInTheDocument();
    expect(screen.getByText("12 Bronze por turno · 3 h · Horário: das 8h às 18h")).toBeInTheDocument();
  });

  it("routes purchases and work through the normal player action flow", async () => {
    const onAction = vi.fn().mockResolvedValue(undefined);
    render(<EconomyPanel campaignId="campaign_1" characterId="character_1" onAction={onAction} />);

    fireEvent.click(await screen.findByRole("button", { name: "18 Bronze" }));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith('Compro "Faca de Ferro" em "Ferraria de Mira"'));

    fireEvent.click(screen.getByRole("button", { name: "Cumprir turno" }));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith('Trabalho no emprego "Ajudante de Ferreiro"'));
  });
});
