import { useMemo, useRef, useState } from "react";

import type { MapViewLocation, MapViewRoute } from "@/types/game";
import {
  discoveryStatusLabel,
  geographicPrecisionLabel,
  locationTypeLabel,
  mapLocationSourceLabel,
} from "@/utils/labels";

/**
 * Phase 20B — Interactive Map Foundation.
 *
 * Renders one region's known locations inside a pannable/zoomable SVG
 * viewport.
 *
 * World-space coordinates (Location.x/y) are normalized once into a
 * fixed 0-100 display space (deterministic — same character knowledge
 * always produces the same layout, per the spec's "map generation must
 * be deterministic" rule); pan/zoom only ever move a *viewBox window*
 * over that fixed space, never recompute node positions.
 *
 * Phase 20D — Geographic Precision & Uncertainty.
 *
 * A location whose resolved precision (app.game.map.view) never
 * reached PRECISE has no authoritative x/y at all (20A already refuses
 * to leak it). Rather than dropping it from the visual map entirely —
 * which would make "vague"/"approximate" Knowledge indistinguishable
 * from "not known at all" — it is placed on a deterministic outer ring
 * (evenly spaced by sorted id, never randomized, never re-derived from
 * the hidden authoritative coordinate) and drawn as a dashed
 * uncertainty circle with a "?" glyph, sized by precision tier. This is
 * a UI affordance, not a claim about position: it never encodes real
 * geography, so it cannot leak any.
 *
 * Phase 20F — Known Routes & Connections.
 *
 * Routes the backend already gated (app.game.map.view — a route only
 * ever ships if both endpoints are visible) are drawn as lines between
 * their placed positions, whichever kind those are (a certain pin or
 * an uncertainty ring) — never a claim about the *geometry* of the
 * road itself, just that a known connection exists between two known
 * places.
 */

const DISPLAY_SIZE = 100;
const DISPLAY_PADDING = 10;
const DISPLAY_CENTER = DISPLAY_SIZE / 2;
const MIN_ZOOM_SPAN = 20;
const MAX_ZOOM_SPAN = 100;
const ZOOM_STEP = 0.8;
const UNCERTAIN_RING_RADIUS = 42;

const UNCERTAINTY_MARKER_RADIUS: Record<string, number> = {
  VAGUE: 6,
  APPROXIMATE: 4,
  GOOD: 2.5,
};
const DEFAULT_UNCERTAINTY_RADIUS = 5;

type PlacedLocation = MapViewLocation & {
  displayX: number;
  displayY: number;
  positionKnown: boolean;
};

type ViewBox = { x: number; y: number; w: number; h: number };

function hasPosition(location: MapViewLocation): location is MapViewLocation & { x: number; y: number } {
  return location.x !== null && location.y !== null;
}

function placeLocations(locations: MapViewLocation[]): PlacedLocation[] {
  const certain = locations.filter(hasPosition);
  const uncertain = [...locations.filter((location) => !hasPosition(location))].sort((a, b) =>
    a.id.localeCompare(b.id),
  );

  const xs = certain.map((location) => location.x);
  const ys = certain.map((location) => location.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const span = DISPLAY_SIZE - DISPLAY_PADDING * 2;

  const placedCertain: PlacedLocation[] = certain.map((location) => {
    const displayX =
      minX === maxX
        ? DISPLAY_CENTER
        : DISPLAY_PADDING + ((location.x - minX) / (maxX - minX)) * span;

    // Y positivo aparece para cima no mapa.
    const displayY =
      minY === maxY
        ? DISPLAY_CENTER
        : DISPLAY_SIZE - DISPLAY_PADDING - ((location.y - minY) / (maxY - minY)) * span;

    return { ...location, displayX, displayY, positionKnown: true };
  });

  const placedUncertain: PlacedLocation[] = uncertain.map((location, index) => {
    const angle = (index / uncertain.length) * 2 * Math.PI;
    return {
      ...location,
      displayX: DISPLAY_CENTER + UNCERTAIN_RING_RADIUS * Math.cos(angle),
      displayY: DISPLAY_CENTER + UNCERTAIN_RING_RADIUS * Math.sin(angle),
      positionKnown: false,
    };
  });

  return [...placedCertain, ...placedUncertain];
}

function clampViewBox(viewBox: ViewBox): ViewBox {
  const w = Math.min(MAX_ZOOM_SPAN, Math.max(MIN_ZOOM_SPAN, viewBox.w));
  const h = Math.min(MAX_ZOOM_SPAN, Math.max(MIN_ZOOM_SPAN, viewBox.h));
  const margin = DISPLAY_SIZE * 0.5;
  const x = Math.min(DISPLAY_SIZE + margin - w, Math.max(-margin, viewBox.x));
  const y = Math.min(DISPLAY_SIZE + margin - h, Math.max(-margin, viewBox.y));
  return { x, y, w, h };
}

export function InteractiveMap({
  locations,
  routes = [],
  onSelect,
}: {
  locations: MapViewLocation[];
  routes?: MapViewRoute[];
  onSelect?: (locationId: string | null) => void;
}) {
  const placed = useMemo(() => placeLocations(locations), [locations]);
  const placedById = useMemo(
    () => Object.fromEntries(placed.map((location) => [location.id, location])),
    [placed],
  );
  const drawableRoutes = useMemo(
    () => routes.filter((route) => placedById[route.from_location_id] && placedById[route.to_location_id]),
    [routes, placedById],
  );

  const [viewBox, setViewBox] = useState<ViewBox>({ x: 0, y: 0, w: DISPLAY_SIZE, h: DISPLAY_SIZE });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragState = useRef<{ startClientX: number; startClientY: number; startViewBox: ViewBox } | null>(null);

  const select = (locationId: string | null) => {
    setSelectedId(locationId);
    onSelect?.(locationId);
  };

  const zoomBy = (factor: number) => {
    setViewBox((current) => {
      const centerX = current.x + current.w / 2;
      const centerY = current.y + current.h / 2;
      const w = current.w * factor;
      const h = current.h * factor;
      return clampViewBox({ x: centerX - w / 2, y: centerY - h / 2, w, h });
    });
  };

  const handlePointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    dragState.current = {
      startClientX: event.clientX,
      startClientY: event.clientY,
      startViewBox: viewBox,
    };
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragState.current;
    if (!drag || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const scaleX = drag.startViewBox.w / rect.width;
    const scaleY = drag.startViewBox.h / rect.height;
    const dx = (event.clientX - drag.startClientX) * scaleX;
    const dy = (event.clientY - drag.startClientY) * scaleY;
    setViewBox(
      clampViewBox({
        ...drag.startViewBox,
        x: drag.startViewBox.x - dx,
        y: drag.startViewBox.y - dy,
      }),
    );
  };

  const handlePointerUp = (event: React.PointerEvent<SVGSVGElement>) => {
    dragState.current = null;
    svgRef.current?.releasePointerCapture(event.pointerId);
  };

  const handleWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    zoomBy(event.deltaY > 0 ? 1 / ZOOM_STEP : ZOOM_STEP);
  };

  if (placed.length === 0) {
    return (
      <p className="panel-empty">
        Nenhum local conhecido para exibir no mapa.
      </p>
    );
  }

  const hovered = hoveredId ? placedById[hoveredId] : null;
  const selected = selectedId ? placedById[selectedId] : null;

  return (
    <div className="interactive-map" data-testid="map-interactive">
      <div className="interactive-map-controls">
        <button
          type="button"
          data-testid="map-zoom-in"
          onClick={() => zoomBy(ZOOM_STEP)}
          aria-label="Aproximar"
        >
          +
        </button>
        <button
          type="button"
          data-testid="map-zoom-out"
          onClick={() => zoomBy(1 / ZOOM_STEP)}
          aria-label="Afastar"
        >
          −
        </button>
      </div>

      <svg
        ref={svgRef}
        className="interactive-map-canvas"
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        onWheel={handleWheel}
        onClick={() => select(null)}
      >
        <g className="interactive-map-routes">
          {drawableRoutes.map((route, index) => {
            const from = placedById[route.from_location_id];
            const to = placedById[route.to_location_id];
            return (
              <line
                key={`${route.from_location_id}-${route.to_location_id}-${index}`}
                data-testid={`map-edge-${route.from_location_id}-${route.to_location_id}`}
                x1={from.displayX}
                y1={from.displayY}
                x2={to.displayX}
                y2={to.displayY}
                className="map-route-line"
              />
            );
          })}
        </g>

        {placed.map((location) => {
          const precisionClass = (location.precision ?? "unknown").toLowerCase();
          const uncertaintyRadius: number = location.precision
            ? (UNCERTAINTY_MARKER_RADIUS[location.precision] ?? DEFAULT_UNCERTAINTY_RADIUS)
            : DEFAULT_UNCERTAINTY_RADIUS;

          return (
            <g
              key={location.id}
              data-testid={`map-node-${location.id}`}
              data-status={location.discovery_status}
              data-selected={location.id === selectedId}
              data-position-known={location.positionKnown}
              transform={`translate(${location.displayX}, ${location.displayY})`}
              onClick={(event) => {
                event.stopPropagation();
                select(location.id);
              }}
              onMouseEnter={() => setHoveredId(location.id)}
              onMouseLeave={() => setHoveredId((current) => (current === location.id ? null : current))}
            >
              {location.positionKnown ? (
                <circle
                  r={location.id === selectedId ? 2.6 : 1.8}
                  className={`map-node-marker precision-${precisionClass}`}
                />
              ) : (
                <>
                  <circle
                    r={uncertaintyRadius}
                    className={`map-node-uncertainty-ring precision-${precisionClass}`}
                  />
                  <text textAnchor="middle" dominantBaseline="central" className="map-node-uncertainty-glyph">
                    ?
                  </text>
                </>
              )}
              <text
                y={location.positionKnown ? -2.5 : -(uncertaintyRadius + 1.5)}
                textAnchor="middle"
                className="map-node-label"
              >
                {location.name ?? "?"}
              </text>
            </g>
          );
        })}
      </svg>

      {hovered && (
        <div className="interactive-map-tooltip" data-testid="map-tooltip">
          {hovered.name ?? "Local desconhecido"}
        </div>
      )}

      {selected && (
        <div className="interactive-map-info" data-testid="map-selected-info">
          <h5>{selected.name ?? "Local desconhecido"}</h5>
          <p>{locationTypeLabel(selected.type)}</p>
          <p>{discoveryStatusLabel(selected.discovery_status)}</p>
          {selected.precision && <p>Precisão: {geographicPrecisionLabel(selected.precision)}</p>}
          {!selected.positionKnown && <p>Posição exata desconhecida.</p>}
          <p>Fonte: {mapLocationSourceLabel(selected.source)}</p>
        </div>
      )}
    </div>
  );
}
