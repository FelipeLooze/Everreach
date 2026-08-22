import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { InteractiveMap } from "@/features/map/InteractiveMap";
import type { MapViewLocation } from "@/types/game";

const locations: MapViewLocation[] = [
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
    x: 4,
    y: 3,
    discovery_status: "DISCOVERED",
  },
];

describe("InteractiveMap", () => {
  afterEach(cleanup);

  it("renders a node per positioned location and omits unpositioned ones", () => {
    render(
      <InteractiveMap
        locations={[
          ...locations,
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
        ]}
      />,
    );

    expect(screen.getByTestId("map-node-location_1")).toBeInTheDocument();
    expect(screen.getByTestId("map-node-location_2")).toBeInTheDocument();
    expect(screen.queryByTestId("map-node-location_3")).not.toBeInTheDocument();
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

  it("renders nothing but a fallback message when no location has a position", () => {
    render(
      <InteractiveMap
        locations={[
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
        ]}
      />,
    );

    expect(
      screen.getByText("Nenhum local possui posição espacial conhecida."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("map-interactive")).not.toBeInTheDocument();
  });
});
