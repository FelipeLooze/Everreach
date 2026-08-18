import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MapPanel } from "@/features/map/MapPanel";

const mocks = vi.hoisted(() => ({
  getMap: vi.fn(),
}));

vi.mock("@/api/map", () => ({
  getMap: mocks.getMap,
}));

describe("MapPanel", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();

    mocks.getMap.mockResolvedValue({
      regions: [
        {
          id: "region_1",
          name: null,
          description: null,
          discovery_status: "DISCOVERED",
        },
      ],
      locations: [
        {
          id: "location_1",
          region_id: "region_1",
          name: null,
          type: "village",
          x: 0,
          y: 0,
          discovery_status: "VISITED",
        },
      ],
      connections: [],
    });
  });

  it("não revela nomes canônicos desconhecidos", async () => {
    render(
      <MapPanel
        campaignId="campaign_1"
        characterId="char_1"
      />
    );

    expect(
      await screen.findByText("Região desconhecida")
    ).toBeInTheDocument();

    expect(
      screen.getByText(/Local desconhecido/)
    ).toBeInTheDocument();

    expect(screen.queryByText("Cardal")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Vale Verdejante")
    ).not.toBeInTheDocument();
  });
});