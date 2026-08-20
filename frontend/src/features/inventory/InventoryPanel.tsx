import { useEffect, useState } from "react";
import { getInventory } from "@/api/inventory";
import type { Inventory } from "@/types/game";

const formatWeight = (value: number) =>
  new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value);

export function InventoryPanel({ campaignId, characterId }: { campaignId: string; characterId: string }) {
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getInventory(campaignId, characterId)
      .then(setInventory)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar o inventário."));
  }, [campaignId, characterId]);

  if (error) return <p className="panel-error">{error}</p>;
  if (!inventory) return <p>Carregando…</p>;

  const encumbranceLabels = {
    NORMAL: "Carga normal",
    LIGHTLY_ENCUMBERED: "Levemente sobrecarregado",
    HEAVILY_ENCUMBERED: "Muito sobrecarregado",
    OVERLOADED: "Carga excessiva",
  };

  return (
    <>
      <p>
        Peso: {formatWeight(inventory.total_weight)} / {formatWeight(inventory.carrying_capacity)} — {encumbranceLabels[inventory.encumbrance]}
      </p>
      {inventory.items.length === 0 ? (
        <p className="panel-empty">O inventário está vazio.</p>
      ) : (
        <ul>
          {inventory.items.map((item) => (
            <li key={item.item_id}>
              {item.name} ({item.type}) × {item.quantity} — {formatWeight(item.total_weight)} de peso {item.equipped && "— equipado"}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
