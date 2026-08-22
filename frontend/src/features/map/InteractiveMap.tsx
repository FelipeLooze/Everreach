import { useMemo, useRef, useState } from "react";

import type { MapViewLocation } from "@/types/game";
import {
  discoveryStatusLabel,
  geographicPrecisionLabel,
  locationTypeLabel,
} from "@/utils/labels";

/**
 * Phase 20B — Interactive Map Foundation.
 *
 * Renders one region's known locations inside a pannable/zoomable SVG
 * viewport. Deliberately locations-only for now: known routes (20F)
 * are a separate future layer, added on top of this same viewBox
 * mechanism rather than by rebuilding it.
 *
 * World-space coordinates (Location.x/y) are normalized once into a
 * fixed 0-100 display space (deterministic — same character knowledge
 * always produces the same layout, per the spec's "map generation must
 * be deterministic" rule); pan/zoom only ever move a *viewBox window*
 * over that fixed space, never recompute node positions.
 */

const DISPLAY_SIZE = 100;
const DISPLAY_PADDING = 10;
const MIN_ZOOM_SPAN = 20;
const MAX_ZOOM_SPAN = 100;
const ZOOM_STEP = 0.8;

type PositionedLocation = MapViewLocation & { displayX: number; displayY: number };

type ViewBox = { x: number; y: number; w: number; h: number };

function normalizePositions(locations: MapViewLocation[]): PositionedLocation[] {
  const known = locations.filter((location) => location.x !== null && location.y !== null);
  if (known.length === 0) {
    return [];
  }

  const xs = known.map((location) => location.x as number);
  const ys = known.map((location) => location.y as number);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const span = DISPLAY_SIZE - DISPLAY_PADDING * 2;

  return known.map((location) => {
    const displayX =
      minX === maxX
        ? DISPLAY_SIZE / 2
        : DISPLAY_PADDING + ((location.x as number) - minX) / (maxX - minX) * span;

    // Y positivo aparece para cima no mapa.
    const displayY =
      minY === maxY
        ? DISPLAY_SIZE / 2
        : DISPLAY_SIZE - DISPLAY_PADDING - ((location.y as number) - minY) / (maxY - minY) * span;

    return { ...location, displayX, displayY };
  });
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
  onSelect,
}: {
  locations: MapViewLocation[];
  onSelect?: (locationId: string | null) => void;
}) {
  const positioned = useMemo(() => normalizePositions(locations), [locations]);
  const positionedById = useMemo(
    () => Object.fromEntries(positioned.map((location) => [location.id, location])),
    [positioned],
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

  if (positioned.length === 0) {
    return (
      <p className="panel-empty">
        Nenhum local possui posição espacial conhecida.
      </p>
    );
  }

  const hovered = hoveredId ? positionedById[hoveredId] : null;
  const selected = selectedId ? positionedById[selectedId] : null;

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
        {positioned.map((location) => (
          <g
            key={location.id}
            data-testid={`map-node-${location.id}`}
            data-status={location.discovery_status}
            data-selected={location.id === selectedId}
            transform={`translate(${location.displayX}, ${location.displayY})`}
            onClick={(event) => {
              event.stopPropagation();
              select(location.id);
            }}
            onMouseEnter={() => setHoveredId(location.id)}
            onMouseLeave={() => setHoveredId((current) => (current === location.id ? null : current))}
          >
            <circle
              r={location.id === selectedId ? 2.6 : 1.8}
              className={`map-node-marker precision-${(location.precision ?? "unknown").toLowerCase()}`}
            />
            <text y={-2.5} textAnchor="middle" className="map-node-label">
              {location.name ?? "?"}
            </text>
          </g>
        ))}
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
        </div>
      )}
    </div>
  );
}
