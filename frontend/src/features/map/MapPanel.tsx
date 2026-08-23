import { useEffect, useState } from "react";

import { createMapAnnotation, deleteMapAnnotation, getMapView, getRoutePlan } from "@/api/map";
import type { MapViewData, RoutePlan } from "@/types/game";
import { InteractiveMap } from "@/features/map/InteractiveMap";
import { connectionTypeLabel, discoveryStatusLabel, locationTypeLabel } from "@/utils/labels";

export function MapPanel({
  campaignId,
  characterId,
}: {
  campaignId: string;
  characterId: string;
}) {
  const [map, setMap] = useState<MapViewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [routePlan, setRoutePlan] = useState<RoutePlan | null>(null);

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

  const locationName = (locationId: string) => {
    const location = map.locations.find((item) => item.id === locationId);
    return location?.name ?? "Local desconhecido";
  };

  const handleCreateAnnotation = (locationId: string, text: string) => {
    createMapAnnotation(campaignId, characterId, locationId, text)
      .then((annotation) => {
        setMap((current) =>
          current ? { ...current, annotations: [...current.annotations, annotation] } : current,
        );
      })
      .catch(() => {
        // Falha silenciosa: a nota simplesmente não aparece; o jogador pode tentar de novo.
      });
  };

  const handleDeleteAnnotation = (annotationId: string) => {
    deleteMapAnnotation(campaignId, characterId, annotationId)
      .then(() => {
        setMap((current) =>
          current
            ? { ...current, annotations: current.annotations.filter((item) => item.id !== annotationId) }
            : current,
        );
      })
      .catch(() => {
        // Falha silenciosa: a nota permanece visível; o jogador pode tentar de novo.
      });
  };

  const handleRequestRoutePlan = (toLocationId: string) => {
    if (!map.position_location_id) return;
    getRoutePlan(campaignId, characterId, map.position_location_id, toLocationId)
      .then(setRoutePlan)
      .catch(() => {
        // Falha silenciosa: o botão "Planejar viagem" continua disponível para nova tentativa.
      });
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
            </header>

            <div className="map-section">
              <h5>Mapa espacial</h5>

              <InteractiveMap
                locations={regionLocations}
                routes={map.routes}
                annotations={map.annotations}
                currentLocationId={map.position_location_id}
                routePlan={routePlan}
                onCreateAnnotation={handleCreateAnnotation}
                onDeleteAnnotation={handleDeleteAnnotation}
                onRequestRoutePlan={handleRequestRoutePlan}
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

        {map.routes.length === 0 ? (
          <p className="panel-empty">
            Nenhuma rota conhecida.
          </p>
        ) : (
          <ul className="map-route-list">
            {map.routes.map((route, index) => {
              const fromName = locationName(route.from_location_id);
              const toName = locationName(route.to_location_id);
              const direction = route.direction ? `${route.direction} →` : "→";

              return (
                <li
                  key={`${route.from_location_id}-${route.to_location_id}-${index}`}
                  className="map-route-item"
                >
                  <div className="map-route-path">
                    <span>{fromName}</span>
                    <span className="map-route-direction">{direction}</span>
                    <span>{toName}</span>
                  </div>

                  <div className="map-route-meta">
                    {connectionTypeLabel(route.connection_type)}
                    {" · distância "}
                    {route.distance}
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
