import { useEffect, useState } from "react";
import { getInventory } from "@/api/inventory";
import type { InventoryItem } from "@/types/game";

export function InventoryPanel({ campaignId, characterId }: { campaignId: string; characterId: string }) {
  const [items, setItems] = useState<InventoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getInventory(campaignId, characterId)
      .then((res) => setItems(res.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar o inventário."));
  }, [campaignId, characterId]);

  if (error) return <p className="panel-error">{error}</p>;
  if (!items) return <p>Carregando…</p>;
  if (items.length === 0) return <p className="panel-empty">O inventário está vazio.</p>;

  return (
    <ul>
      {items.map((item) => (
        <li key={item.item_id}>
          {item.name} ({item.type}) × {item.quantity} {item.equipped && "— equipado"}
        </li>
      ))}
    </ul>
  );
}
