import { useEffect, useState } from "react";
import { getMap } from "@/api/map";
import type { MapData } from "@/types/game";
import { discoveryStatusLabel, locationTypeLabel } from "@/utils/labels";

/* Placeholder em texto. Um renderizador futuro com PixiJS consumirá o mesmo
   endpoint /map — este painel propositalmente não implementa renderização gráfica. */
export function MapPanel({ campaignId, characterId }: { campaignId: string; characterId: string; }) {
  const [map, setMap] = useState<MapData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMap(campaignId, characterId)
      .then(setMap)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar o mapa."));
  }, [campaignId, characterId]);

  if (error) return <p className="panel-error">{error}</p>;
  if (!map) return <p>Carregando…</p>;
  if (map.regions.length === 0) return <p className="panel-empty">O mapa está vazio. Inicie o mundo para revelá-lo.</p>;

  return (
    <div>
      {map.regions.map((region) => (
        <div key={region.id} className="map-region">
          <h4>{region.name ?? "Região desconhecida"}</h4>
          {region.description && <p>{region.description}</p>}
          <ul>
            {map.locations
              .filter((loc) => loc.region_id === region.id)
              .map((loc) => (
                <li key={loc.id}>
                  {loc.name ?? "Local desconhecido"} ({locationTypeLabel(loc.type)}) —{" "}
                  {discoveryStatusLabel(loc.discovery_status)}
                </li>
              ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
