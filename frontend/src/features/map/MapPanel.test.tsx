import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MapPanel } from "@/features/map/MapPanel";

const mocks = vi.hoisted(() => ({
  getMapView: vi.fn(),
  createMapAnnotation: vi.fn(),
  deleteMapAnnotation: vi.fn(),
}));

vi.mock("@/api/map", () => ({
  getMapView: mocks.getMapView,
  createMapAnnotation: mocks.createMapAnnotation,
  deleteMapAnnotation: mocks.deleteMapAnnotation,
}));

describe("MapPanel", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();

    mocks.getMapView.mockResolvedValue({
      campaign_id: "campaign_1",
      character_id: "char_1",
      scope: null,
      regions: [
        {
          id: "region_1",
          name: null,
          discovery_status: "DISCOVERED",
        },
      ],
      locations: [
        {
          id: "location_1",
          region_id: "region_1",
          type: "village",
          name: null,
          precision: "PRECISE",
          x: 0,
          y: 0,
          discovery_status: "VISITED",
        },
      ],
      routes: [],
      annotations: [],
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
      screen.getAllByText(/Local desconhecido/).length
    ).toBeGreaterThan(0);

    expect(screen.queryByText("Cardal")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Vale Verdejante")
    ).not.toBeInTheDocument();
  });

  it("mostra locais conhecidos por região", async () => {
    mocks.getMapView.mockResolvedValue({
      campaign_id: "campaign_1",
      character_id: "char_1",
      scope: null,
      regions: [
        {
          id: "region_1",
          name: "Vale Verdejante",
          discovery_status: "DISCOVERED",
        },
      ],
      locations: [
        {
          id: "location_1",
          region_id: "region_1",
          type: "village",
          name: "Cardal",
          precision: "PRECISE",
          x: 0,
          y: 0,
          discovery_status: "VISITED",
        },
        {
          id: "location_2",
          region_id: "region_1",
          type: "forest",
          name: "Bosque da Beira do Vale",
          precision: "APPROXIMATE",
          x: -2,
          y: 1,
          discovery_status: "DISCOVERED",
        },
      ],
      routes: [
        {
          from_location_id: "location_1",
          to_location_id: "location_2",
          direction: "noroeste",
          connection_type: "PATH",
          distance: 1,
          danger: 1,
        },
      ],
      annotations: [],
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

    expect(screen.getByText("Rotas conhecidas")).toBeInTheDocument();
    expect(screen.getByText("noroeste →")).toBeInTheDocument();
    expect(screen.getByText("trilha · distância 1")).toBeInTheDocument();
    expect(
      screen.getByTestId("map-edge-location_1-location_2"),
    ).toBeInTheDocument();

    expect(screen.getAllByText("Cardal").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Bosque da Beira do Vale").length).toBeGreaterThan(0);
  });

  it("desenha apenas locais com posição conhecida", async () => {
    mocks.getMapView.mockResolvedValue({
      campaign_id: "campaign_1",
      character_id: "char_1",
      scope: null,
      regions: [
        {
          id: "region_1",
          name: null,
          discovery_status: "DISCOVERED",
        },
      ],
      locations: [
        {
          id: "location_1",
          region_id: "region_1",
          type: "village",
          name: "Cardal",
          precision: "PRECISE",
          x: 0,
          y: 0,
          discovery_status: "VISITED",
        },
        {
          id: "location_2",
          region_id: "region_1",
          type: "forest",
          name: "Bosque",
          precision: "APPROXIMATE",
          x: -2,
          y: 1,
          discovery_status: "DISCOVERED",
        },
        {
          id: "location_3",
          region_id: "region_1",
          type: "generic",
          name: null,
          precision: "VAGUE",
          x: null,
          y: null,
          discovery_status: "RUMORED",
        },
      ],
      routes: [],
      annotations: [],
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
      screen.getByTestId("map-node-location_3"),
    ).toHaveAttribute("data-position-known", "false");

    expect(
      screen.getByText(
        "Alguns locais conhecidos ainda não possuem posição precisa.",
      ),
    ).toBeInTheDocument();
  });

  it("creates and then deletes an annotation through the API", async () => {
    mocks.createMapAnnotation.mockResolvedValue({
      id: "annotation_1",
      location_id: "location_1",
      text: "Bom poço.",
      created_at: "2026-01-01T00:00:00",
    });
    mocks.deleteMapAnnotation.mockResolvedValue({ deleted: true });

    render(
      <MapPanel
        campaignId="campaign_1"
        characterId="char_1"
      />,
    );

    fireEvent.click(await screen.findByTestId("map-node-location_1"));
    fireEvent.change(screen.getByLabelText("Nova anotação"), { target: { value: "Bom poço." } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    expect(mocks.createMapAnnotation).toHaveBeenCalledWith(
      "campaign_1", "char_1", "location_1", "Bom poço.",
    );
    expect(await screen.findByTestId("map-annotation-annotation_1")).toHaveTextContent("Bom poço.");

    fireEvent.click(screen.getByRole("button", { name: "Apagar anotação" }));

    expect(mocks.deleteMapAnnotation).toHaveBeenCalledWith("campaign_1", "char_1", "annotation_1");
    await waitFor(() =>
      expect(screen.queryByTestId("map-annotation-annotation_1")).not.toBeInTheDocument(),
    );
  });
});
