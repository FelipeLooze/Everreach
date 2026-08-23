import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { InteractiveMap } from "@/features/map/InteractiveMap";
import type { MapViewAnnotation, MapViewLocation, MapViewRoute, RoutePlan } from "@/types/game";

const locations: MapViewLocation[] = [
  {
    id: "location_1",
    region_id: "region_1",
    subregion_id: null,
    parent_location_id: null,
    known_aspects: ["EXISTENCE"],
    source: "discovery",
    stale: false,
    provenance: null,
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
    parent_location_id: null,
    known_aspects: ["EXISTENCE"],
    source: "discovery",
    stale: false,
    provenance: null,
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

  it("draws a line for a route whose endpoints are both visible", () => {
    const routes: MapViewRoute[] = [
      {
        from_location_id: "location_1",
        to_location_id: "location_2",
        direction: "leste",
        connection_type: "PATH",
        distance: 3,
        danger: 0,
        travel_time_modifier: 1,
      },
    ];

    render(<InteractiveMap locations={locations} routes={routes} />);

    expect(screen.getByTestId("map-edge-location_1-location_2")).toBeInTheDocument();
  });

  it("omits a route whose endpoint is not among the visible locations", () => {
    const routes: MapViewRoute[] = [
      {
        from_location_id: "location_1",
        to_location_id: "location_never_shown",
        direction: null,
        connection_type: "PATH",
        distance: 3,
        danger: 0,
        travel_time_modifier: 1,
      },
    ];

    render(<InteractiveMap locations={locations} routes={routes} />);

    expect(screen.queryByTestId("map-edge-location_1-location_never_shown")).not.toBeInTheDocument();
  });

  it("renders a node for every location, positioned or not", () => {
    render(
      <InteractiveMap
        locations={[
          ...locations,
          {
            id: "location_3",
            region_id: "region_1",
            subregion_id: null,
            parent_location_id: null,
            known_aspects: ["EXISTENCE"],
            source: "discovery",
            stale: false,
            provenance: null,
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
            parent_location_id: null,
            known_aspects: ["EXISTENCE"],
            source: "discovery",
            stale: false,
            provenance: null,
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
            parent_location_id: null,
            known_aspects: ["EXISTENCE"],
            source: "discovery",
            stale: false,
            provenance: null,
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
            parent_location_id: null,
            known_aspects: ["EXISTENCE"],
            source: "discovery",
            stale: false,
            provenance: null,
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

  it("shows a dot on a location that has an annotation", () => {
    const annotations: MapViewAnnotation[] = [
      { id: "annotation_1", location_id: "location_1", text: "Bom poço.", created_at: "2026-01-01T00:00:00" },
    ];

    render(<InteractiveMap locations={locations} annotations={annotations} />);

    expect(screen.getByTestId("map-node-annotation-dot-location_1")).toBeInTheDocument();
    expect(screen.queryByTestId("map-node-annotation-dot-location_2")).not.toBeInTheDocument();
  });

  it("lists a selected location's annotations with a delete button", () => {
    const annotations: MapViewAnnotation[] = [
      { id: "annotation_1", location_id: "location_1", text: "Bom poço.", created_at: "2026-01-01T00:00:00" },
    ];
    let deletedId: string | null = null;

    render(
      <InteractiveMap
        locations={locations}
        annotations={annotations}
        onDeleteAnnotation={(id) => {
          deletedId = id;
        }}
      />,
    );

    fireEvent.click(screen.getByTestId("map-node-location_1"));

    expect(screen.getByTestId("map-annotation-annotation_1")).toHaveTextContent("Bom poço.");

    fireEvent.click(screen.getByRole("button", { name: "Apagar anotação" }));
    expect(deletedId).toBe("annotation_1");
  });

  it("submits a new annotation for the selected location", () => {
    let created: { locationId: string; text: string } | null = null;

    render(
      <InteractiveMap
        locations={locations}
        onCreateAnnotation={(locationId, text) => {
          created = { locationId, text };
        }}
      />,
    );

    fireEvent.click(screen.getByTestId("map-node-location_2"));
    fireEvent.change(screen.getByLabelText("Nova anotação"), { target: { value: "Cuidado com lobos." } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    expect(created).toEqual({ locationId: "location_2", text: "Cuidado com lobos." });
  });

  it("does not submit an empty annotation", () => {
    let called = false;

    render(
      <InteractiveMap
        locations={locations}
        onCreateAnnotation={() => {
          called = true;
        }}
      />,
    );

    fireEvent.click(screen.getByTestId("map-node-location_1"));
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    expect(called).toBe(false);
  });

  it("shows a staleness note for a stale map-sourced location", () => {
    render(
      <InteractiveMap
        locations={[
          { ...locations[0], source: "map", stale: true },
        ]}
      />,
    );

    fireEvent.click(screen.getByTestId("map-node-location_1"));

    expect(screen.getByTestId("map-selected-stale")).toBeInTheDocument();
    expect(screen.getByTestId("map-node-location_1")).toHaveAttribute("data-stale", "true");
  });

  it("does not show a staleness note for a fresh location", () => {
    render(<InteractiveMap locations={locations} />);

    fireEvent.click(screen.getByTestId("map-node-location_1"));

    expect(screen.queryByTestId("map-selected-stale")).not.toBeInTheDocument();
  });

  it("marks the character's current location with a position ring", () => {
    render(<InteractiveMap locations={locations} currentLocationId="location_1" />);

    expect(screen.getByTestId("map-node-location_1")).toHaveAttribute("data-current-position", "true");
    expect(screen.getByTestId("map-current-position-marker")).toBeInTheDocument();
  });

  it("shows no position ring when currentLocationId is not among the visible locations", () => {
    render(<InteractiveMap locations={locations} currentLocationId="location_never_shown" />);

    expect(screen.queryByTestId("map-current-position-marker")).not.toBeInTheDocument();
  });

  it("offers to plan a route from the character's current position to a different selected location", () => {
    let requestedTo: string | null = null;

    render(
      <InteractiveMap
        locations={locations}
        currentLocationId="location_1"
        onRequestRoutePlan={(toLocationId) => {
          requestedTo = toLocationId;
        }}
      />,
    );

    fireEvent.click(screen.getByTestId("map-node-location_2"));
    fireEvent.click(screen.getByTestId("map-plan-route"));

    expect(requestedTo).toBe("location_2");
  });

  it("does not offer to plan a route to the character's own current location", () => {
    render(
      <InteractiveMap locations={locations} currentLocationId="location_1" onRequestRoutePlan={() => {}} />,
    );

    fireEvent.click(screen.getByTestId("map-node-location_1"));

    expect(screen.queryByTestId("map-plan-route")).not.toBeInTheDocument();
  });

  it("shows the fetched route plan for the selected destination", () => {
    const routePlan: RoutePlan = {
      known: true,
      from_location_id: "location_1",
      to_location_id: "location_2",
      segments: [
        { from_location_id: "location_1", to_location_id: "location_2", direction: "leste", connection_type: "PATH", distance: 3, danger: 0 },
      ],
      total_distance: 3,
      estimated_minutes: 45,
      max_danger: 0,
    };

    render(
      <InteractiveMap
        locations={locations}
        currentLocationId="location_1"
        routePlan={routePlan}
        onRequestRoutePlan={() => {}}
      />,
    );

    fireEvent.click(screen.getByTestId("map-node-location_2"));

    expect(screen.getByTestId("map-route-plan-result")).toHaveTextContent("Tempo estimado: 45 min");
  });

  it("shows 'no known route' when the fetched plan says the route is unknown", () => {
    const routePlan: RoutePlan = {
      known: false,
      from_location_id: "location_1",
      to_location_id: "location_2",
      segments: [],
      total_distance: 0,
      estimated_minutes: 0,
      max_danger: 0,
    };

    render(
      <InteractiveMap
        locations={locations}
        currentLocationId="location_1"
        routePlan={routePlan}
        onRequestRoutePlan={() => {}}
      />,
    );

    fireEvent.click(screen.getByTestId("map-node-location_2"));

    expect(screen.getByTestId("map-route-plan-result")).toHaveTextContent("Nenhuma rota conhecida");
  });

  it("shows the location's knowledge provenance when present", () => {
    render(
      <InteractiveMap
        locations={[{ ...locations[0], provenance: "revelado por Mira" }]}
      />,
    );

    fireEvent.click(screen.getByTestId("map-node-location_1"));

    expect(screen.getByTestId("map-selected-provenance")).toHaveTextContent("revelado por Mira");
  });

  it("does not show a provenance line when none is known", () => {
    render(<InteractiveMap locations={locations} />);

    fireEvent.click(screen.getByTestId("map-node-location_1"));

    expect(screen.queryByTestId("map-selected-provenance")).not.toBeInTheDocument();
  });
});
