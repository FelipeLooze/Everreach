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

  it("mostra locais e rotas conhecidas", async () => {
    mocks.getMap.mockResolvedValue({
        regions: [
        {
            id: "region_1",
            name: "Vale Verdejante",
            description: null,
            discovery_status: "DISCOVERED",
        },
        ],
        locations: [
        {
            id: "location_1",
            region_id: "region_1",
            name: "Cardal",
            type: "village",
            x: 0,
            y: 0,
            discovery_status: "VISITED",
        },
        {
            id: "location_2",
            region_id: "region_1",
            name: "Bosque da Beira do Vale",
            type: "forest",
            x: -2,
            y: 1,
            discovery_status: "DISCOVERED",
        },
        ],
        connections: [
        {
            from_location_id: "location_1",
            to_location_id: "location_2",
            direction: "noroeste",
            connection_type: "PATH",
            distance: 1,
            danger: 1,
            travel_time_modifier: 1,
        },
        ],
    });

    render(
        <MapPanel
        campaignId="campaign_1"
        characterId="char_1"
        />,
    );

    expect(
        await screen.findByText("Vale Verdejante"),
    ).toBeInTheDocument();

    expect(screen.getAllByText("Cardal").length).toBeGreaterThan(0);

    expect(screen.getAllByText("Bosque da Beira do Vale").length).toBeGreaterThan(0);

    expect(
        screen.getByText("Rotas conhecidas"),
    ).toBeInTheDocument();

    expect(
        screen.getByText("noroeste →"),
    ).toBeInTheDocument();

    expect(
        screen.getByText("trilha · distância 1"),
    ).toBeInTheDocument();
    });

  it("desenha apenas locais com posição conhecida", async () => {
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
          name: "Cardal",
          type: "village",
          x: 0,
          y: 0,
          discovery_status: "VISITED",
        },
        {
          id: "location_2",
          region_id: "region_1",
          name: "Bosque",
          type: "forest",
          x: -2,
          y: 1,
          discovery_status: "DISCOVERED",
        },
        {
          id: "location_3",
          region_id: "region_1",
          name: null,
          type: "generic",
          x: null,
          y: null,
          discovery_status: "RUMORED",
        },
      ],
      connections: [
        {
          from_location_id: "location_1",
          to_location_id: "location_2",
          direction: "noroeste",
          connection_type: "PATH",
          distance: 1,
          danger: 1,
          travel_time_modifier: 1,
        },
      ],
    });

    render(
      <MapPanel
        campaignId="campaign_1"
        characterId="char_1"
      />,
    );

    expect(
      await screen.findByText("Mapa espacial"),
    ).toBeInTheDocument();

    expect(
      screen.getByTestId("map-node-location_1"),
    ).toBeInTheDocument();

    expect(
      screen.getByTestId("map-node-location_2"),
    ).toBeInTheDocument();

    expect(
      screen.queryByTestId("map-node-location_3"),
    ).not.toBeInTheDocument();

    expect(
      screen.getByTestId(
        "map-edge-location_1-location_2",
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "Alguns locais conhecidos ainda não possuem posição precisa.",
      ),
    ).toBeInTheDocument();
  });

});