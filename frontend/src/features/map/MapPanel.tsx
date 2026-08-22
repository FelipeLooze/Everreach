import { useEffect, useState } from "react";

import { getMapView } from "@/api/map";
import type { MapViewData } from "@/types/game";
import { InteractiveMap } from "@/features/map/InteractiveMap";
import { discoveryStatusLabel, locationTypeLabel } from "@/utils/labels";

export function MapPanel({
  campaignId,
  characterId,
}: {
  campaignId: string;
  characterId: string;
}) {
  const [map, setMap] = useState<MapViewData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMapView(campaignId, characterId)
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
            </header>

            <div className="map-section">
              <h5>Mapa espacial</h5>

              <InteractiveMap locations={regionLocations} />

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
    </div>
  );
}
