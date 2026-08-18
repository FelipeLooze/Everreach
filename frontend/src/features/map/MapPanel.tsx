import { useEffect, useState } from "react";

import { getMap } from "@/api/map";
import type { MapData, MapLocation } from "@/types/game";
import {
  connectionTypeLabel,
  discoveryStatusLabel,
  locationTypeLabel,
} from "@/utils/labels";

type PositionedLocation = MapLocation & {
  x: number;
  y: number;
};

function hasCoordinates(
  location: MapLocation,
): location is PositionedLocation {
  return location.x !== null && location.y !== null;
}

function RegionSpatialMap({
  locations,
  map,
}: {
  locations: MapLocation[];
  map: MapData;
}) {
  const positionedLocations = locations.filter(hasCoordinates);

  if (positionedLocations.length === 0) {
    return (
      <p className="panel-empty">
        Nenhum local possui posição espacial conhecida.
      </p>
    );
  }

  const xs = positionedLocations.map((location) => location.x);
  const ys = positionedLocations.map((location) => location.y);

  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const positionOf = (location: PositionedLocation) => {
    const left =
      minX === maxX
        ? 50
        : 10 + ((location.x - minX) / (maxX - minX)) * 80;

    // Y positivo aparece para cima no mapa.
    const top =
      minY === maxY
        ? 50
        : 90 - ((location.y - minY) / (maxY - minY)) * 80;

    return {
      left,
      top,
    };
  };

  const positionedById = Object.fromEntries(
    positionedLocations.map((location) => [
      location.id,
      location,
    ]),
  ) as Record<string, PositionedLocation>;

  const drawableConnections = map.connections.filter(
    (connection) =>
      positionedById[connection.from_location_id] &&
      positionedById[connection.to_location_id],
  );

  return (
    <div className="map-canvas">
      <svg
        className="map-edges"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {drawableConnections.map((connection, index) => {
          const from = positionedById[
            connection.from_location_id
          ];
          const to = positionedById[
            connection.to_location_id
          ];

          const fromPosition = positionOf(from);
          const toPosition = positionOf(to);

          return (
            <line
              key={`${connection.from_location_id}-${connection.to_location_id}-${index}`}
              data-testid={`map-edge-${connection.from_location_id}-${connection.to_location_id}`}
              x1={fromPosition.left}
              y1={fromPosition.top}
              x2={toPosition.left}
              y2={toPosition.top}
            />
          );
        })}
      </svg>

      {positionedLocations.map((location) => {
        const position = positionOf(location);

        return (
          <div
            key={location.id}
            className="map-node"
            data-testid={`map-node-${location.id}`}
            data-status={location.discovery_status}
            style={{
              left: `${position.left}%`,
              top: `${position.top}%`,
            }}
          >
            <span className="map-node-marker" />

            <span className="map-node-label">
              {location.name ?? "?"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function MapPanel({
  campaignId,
  characterId,
}: {
  campaignId: string;
  characterId: string;
}) {
  const [map, setMap] = useState<MapData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMap(campaignId, characterId)
      .then(setMap)
      .catch((err) =>
        setError(
          err instanceof Error
            ? err.message
            : "Falha ao carregar o mapa.",
        ),
      );
  }, [campaignId, characterId]);

  if (error) {
    return <p className="panel-error">{error}</p>;
  }

  if (!map) {
    return <p>Carregando…</p>;
  }

  if (map.regions.length === 0) {
    return (
      <p className="panel-empty">
        Nenhum local foi descoberto ainda.
      </p>
    );
  }

  const locationName = (locationId: string) => {
    const location = map.locations.find(
      (item) => item.id === locationId,
    );

    return location?.name ?? "Local desconhecido";
  };

  return (
    <div className="exploration-map">
      {map.regions.map((region) => {
        const regionLocations = map.locations.filter(
          (location) => location.region_id === region.id,
        );

        return (
          <section key={region.id} className="map-region">
            <header className="map-region-header">
              <h4>
                {region.name ?? "Região desconhecida"}
              </h4>

              {region.description && (
                <p>{region.description}</p>
              )}
            </header>

            <div className="map-section">
              <h5>Mapa espacial</h5>

              <RegionSpatialMap
                locations={regionLocations}
                map={map}
              />

              {regionLocations.some(
                (location) =>
                  location.x === null || location.y === null,
              ) && (
                <p className="map-position-note">
                  Alguns locais conhecidos ainda não possuem
                  posição precisa.
                </p>
              )}
            </div>

            <div className="map-section">
              <h5>Locais conhecidos</h5>

              {regionLocations.length === 0 ? (
                <p className="panel-empty">
                  Nenhum local conhecido nesta região.
                </p>
              ) : (
                <ul className="map-location-list">
                  {regionLocations.map((location) => (
                    <li
                      key={location.id}
                      className="map-location-item"
                    >
                      <span className="map-location-name">
                        {location.name ??
                          "Local desconhecido"}
                      </span>

                      <span className="map-location-meta">
                        {locationTypeLabel(location.type)}
                        {" · "}
                        {discoveryStatusLabel(
                          location.discovery_status,
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        );
      })}

      <section className="map-section map-routes">
        <h4>Rotas conhecidas</h4>

        {map.connections.length === 0 ? (
          <p className="panel-empty">
            Nenhuma rota conhecida.
          </p>
        ) : (
          <ul className="map-route-list">
            {map.connections.map((connection, index) => {
              const fromName = locationName(
                connection.from_location_id,
              );

              const toName = locationName(
                connection.to_location_id,
              );

              const direction = connection.direction
                ? `${connection.direction} →`
                : "→";

              return (
                <li
                  key={`${connection.from_location_id}-${connection.to_location_id}-${index}`}
                  className="map-route-item"
                >
                  <div className="map-route-path">
                    <span>{fromName}</span>

                    <span className="map-route-direction">
                      {direction}
                    </span>

                    <span>{toName}</span>
                  </div>

                  <div className="map-route-meta">
                    {connectionTypeLabel(
                      connection.connection_type,
                    )}
                    {" · distância "}
                    {connection.distance}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}