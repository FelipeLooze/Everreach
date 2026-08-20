import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JournalPanel } from "@/features/journal/JournalPanel";

const mocks = vi.hoisted(() => ({ getJournal: vi.fn() }));

vi.mock("@/api/journal", () => ({ getJournal: mocks.getJournal }));

describe("JournalPanel", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getJournal.mockResolvedValue({
      memories: [
        {
          id: "memory_1",
          subject: "npc:osgar",
          summary_text: "Conversou com Osgar.",
          importance: 3,
          source_event_id: "event_1",
          created_at: "2026-08-15T12:00:00Z",
        },
      ],
      events: [
        {
          id: "event_1",
          event_type: "RELATIONSHIP_CHANGED",
          actor_type: "character",
          actor_id: "character_1",
          world_minute: 10,
          importance: 2,
          created_at: "2026-08-15T12:00:00Z",
        },
      ],
    });
  });

  it("carrega somente o diário do personagem selecionado", async () => {
    render(<JournalPanel campaignId="campaign_1" characterId="character_1" />);

    await waitFor(() =>
      expect(mocks.getJournal).toHaveBeenCalledWith("campaign_1", "character_1"),
    );
    expect(await screen.findByText(/Conversou com Osgar/)).toBeInTheDocument();
    expect(screen.getByText(/importância 3/i)).toBeInTheDocument();
    expect(screen.getByText("Uma relação mudou")).toBeInTheDocument();
  });
});
