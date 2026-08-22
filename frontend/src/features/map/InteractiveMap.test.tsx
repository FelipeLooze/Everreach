import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { InteractiveMap } from "@/features/map/InteractiveMap";
import type { MapViewLocation } from "@/types/game";

const locations: MapViewLocation[] = [
  {
    id: "location_1",
    region_id: "region_1",
    subregion_id: null,
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
    subregion_id: null,
    type: "forest",
    name: "Bosque",
    precision: "APPROXIMATE",
    x: 4,
    y: 3,
    discovery_status: "DISCOVERED",
  },
];

describe("InteractiveMap", () => {
  afterEach(cleanup);

  it("renders a node for every location, positioned or not", () => {
    render(
      <InteractiveMap
        locations={[
          ...locations,
          {
            id: "location_3",
            region_id: "region_1",
            subregion_id: null,
            type: "generic",
            name: null,
            precision: "VAGUE",
            x: null,
            y: null,
            discovery_status: "RUMORED",
          },
        ]}
      />,
    );

    expect(screen.getByTestId("map-node-location_1")).toBeInTheDocument();
    expect(screen.getByTestId("map-node-location_2")).toBeInTheDocument();
    expect(screen.getByTestId("map-node-location_3")).toBeInTheDocument();
  });

  it("marks a location with no known exact position as position-unknown, distinct from positioned ones", () => {
    render(
      <InteractiveMap
        locations={[
          ...locations,
          {
            id: "location_3",
            region_id: "region_1",
            subregion_id: null,
            type: "generic",
            name: null,
            precision: "VAGUE",
            x: null,
            y: null,
            discovery_status: "RUMORED",
          },
        ]}
      />,
    );

    expect(screen.getByTestId("map-node-location_1")).toHaveAttribute("data-position-known", "true");
    expect(screen.getByTestId("map-node-location_3")).toHaveAttribute("data-position-known", "false");
  });

  it("selecting an uncertain location's info panel says its exact position is unknown", () => {
    render(
      <InteractiveMap
        locations={[
          {
            id: "location_3",
            region_id: "region_1",
            subregion_id: null,
            type: "generic",
            name: null,
            precision: "VAGUE",
            x: null,
            y: null,
            discovery_status: "RUMORED",
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByTestId("map-node-location_3"));

    expect(screen.getByTestId("map-selected-info")).toHaveTextContent("Posição exata desconhecida.");
  });

  it("selecting a node shows its known information panel", () => {
    render(<InteractiveMap locations={locations} />);

    fireEvent.click(screen.getByTestId("map-node-location_1"));

    const info = screen.getByTestId("map-selected-info");
    expect(info).toHaveTextContent("Cardal");
    expect(info).toHaveTextContent("visitado");
  });

  it("clicking empty map space clears the selection", () => {
    render(<InteractiveMap locations={locations} />);

    fireEvent.click(screen.getByTestId("map-node-location_1"));
    expect(screen.getByTestId("map-selected-info")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("map-interactive").querySelector("svg")!);
    expect(screen.queryByTestId("map-selected-info")).not.toBeInTheDocument();
  });

  it("hovering a node shows a tooltip with its known name", () => {
    render(<InteractiveMap locations={locations} />);

    fireEvent.mouseEnter(screen.getByTestId("map-node-location_2"));
    expect(screen.getByTestId("map-tooltip")).toHaveTextContent("Bosque");

    fireEvent.mouseLeave(screen.getByTestId("map-node-location_2"));
    expect(screen.queryByTestId("map-tooltip")).not.toBeInTheDocument();
  });

  it("zoom controls narrow and widen the viewBox", () => {
    render(<InteractiveMap locations={locations} />);

    const svg = screen.getByTestId("map-interactive").querySelector("svg")!;
    const initialViewBox = svg.getAttribute("viewBox");

    fireEvent.click(screen.getByTestId("map-zoom-in"));
    expect(svg.getAttribute("viewBox")).not.toBe(initialViewBox);

    fireEvent.click(screen.getByTestId("map-zoom-out"));
  });

  it("shows a fallback message only when there are no known locations at all", () => {
    render(<InteractiveMap locations={[]} />);

    expect(
      screen.getByText("Nenhum local conhecido para exibir no mapa."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("map-interactive")).not.toBeInTheDocument();
  });

  it("still renders the map when every known location is uncertain (no positioned locations at all)", () => {
    render(
      <InteractiveMap
        locations={[
          {
            id: "location_3",
            region_id: "region_1",
            subregion_id: null,
            type: "generic",
            name: null,
            precision: "VAGUE",
            x: null,
            y: null,
            discovery_status: "RUMORED",
          },
        ]}
      />,
    );

    expect(screen.getByTestId("map-interactive")).toBeInTheDocument();
    expect(screen.getByTestId("map-node-location_3")).toBeInTheDocument();
  });
});
