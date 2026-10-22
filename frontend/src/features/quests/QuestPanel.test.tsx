import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QuestPanel } from "@/features/quests/QuestPanel";

const mocks = vi.hoisted(() => ({
  getQuests: vi.fn(),
  acceptQuest: vi.fn(),
  abandonQuest: vi.fn(),
}));

vi.mock("@/api/quests", () => mocks);

const availableQuest = {
  quest_id: "quest_1",
  name: "Relato da Primeira Chegada",
  description: "Converse com o ancião.",
  status: "AVAILABLE",
  objectives: [{ id: "objective_1", description: "Falar com o ancião.", completed: false }],
};

describe("QuestPanel", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows discovered opportunities and accepts one", async () => {
    mocks.getQuests
      .mockResolvedValueOnce({ quests: [availableQuest] })
      .mockResolvedValueOnce({ quests: [{ ...availableQuest, status: "ACTIVE" }] });
    mocks.acceptQuest.mockResolvedValue({ ...availableQuest, status: "ACTIVE" });

    render(<QuestPanel campaignId="campaign_1" characterId="character_1" />);

    expect(await screen.findByText("Relato da Primeira Chegada", { exact: false })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Aceitar missão" }));

    await waitFor(() => {
      expect(mocks.acceptQuest).toHaveBeenCalledWith("campaign_1", "character_1", "quest_1");
      expect(screen.getByRole("button", { name: "Abandonar missão" })).toBeInTheDocument();
    });
  });

  it("keeps an action error visible without discarding the quest list", async () => {
    mocks.getQuests.mockResolvedValue({ quests: [availableQuest] });
    mocks.acceptQuest.mockRejectedValue(new Error("Contrato já foi aceito por outra pessoa."));

    render(<QuestPanel campaignId="campaign_1" characterId="character_1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Aceitar missão" }));

    expect(await screen.findByText("Contrato já foi aceito por outra pessoa.")).toBeInTheDocument();
    expect(screen.getByText("Relato da Primeira Chegada", { exact: false })).toBeInTheDocument();
  });
});
