import { useEffect, useState } from "react";

import { getMap } from "@/api/map";
import type { MapData } from "@/types/game";
import {
  connectionTypeLabel,
  discoveryStatusLabel,
  locationTypeLabel,
} from "@/utils/labels";

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
              <h4>{region.name ?? "Região desconhecida"}</h4>

              {region.description && (
                <p>{region.description}</p>
              )}
            </header>

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
                        {location.name ?? "Local desconhecido"}
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