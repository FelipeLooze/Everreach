import { useEffect, useState } from "react";
import { getInventory } from "@/api/inventory";
import { StateBadge, type StateTone } from "@/components/StateBadge";
import type { Inventory, InventoryItem } from "@/types/game";

const formatWeight = (value: number) =>
  new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value);

const equipmentSlotLabels = {
  HEAD: "cabeça",
  TORSO: "torso",
  LEGS: "pernas",
  FEET: "pés",
  HANDS: "mãos",
  MAIN_HAND: "mão principal",
  OFF_HAND: "mão secundária",
  BOTH_HANDS: "duas mãos",
  BACK: "costas",
  WAIST: "cintura",
  ACCESSORY: "acessório",
};

const accessibilityLabels = {
  IMMEDIATE: "uso imediato",
  QUICK: "acesso rápido",
  WORN: "vestido",
  STOWED: "guardado",
};

const qualityLabels = {
  CRUDE: "rudimentar",
  POOR: "ruim",
  STANDARD: "padrão",
  GOOD: "boa",
  EXCELLENT: "excelente",
  MASTERWORK: "obra-prima",
};

const conditionLabels = {
  EXCELLENT: "excelente",
  GOOD: "boa",
  WORN: "desgastada",
  DAMAGED: "danificada",
  CRITICAL: "crítica",
  BROKEN: "quebrada",
};

// Phase 21L/21P — condition is real backend state (durability), never
// MMO rarity: the tone reflects how urgent the wear is, not how
// "special" the item is.
const conditionTone: Record<keyof typeof conditionLabels, StateTone> = {
  EXCELLENT: "success",
  GOOD: "success",
  WORN: "warning",
  DAMAGED: "warning",
  CRITICAL: "danger",
  BROKEN: "danger",
};

const weaponFamilyLabels = {
  DAGGER: "adaga",
  KNIFE: "faca",
  SWORD: "espada",
  AXE: "machado",
  HAMMER: "martelo",
  MACE: "maça",
  SPEAR: "lança",
  POLEARM: "arma de haste",
  BOW: "arco",
  CROSSBOW: "besta",
  SLING: "funda",
  STAFF: "bastão",
  CLUB: "clava",
};

const damageProfileLabels = {
  SLASH: "corte",
  PIERCE: "perfuração",
  BLUNT: "impacto",
};

const bodyAreaLabels = {
  HEAD: "cabeça",
  TORSO: "torso",
  ARMS: "braços",
  HANDS: "mãos",
  LEGS: "pernas",
  FEET: "pés",
};

const weaponReachLabels = {
  NORMAL: "alcance normal",
  LONG: "alcance longo",
  RANGED: "à distância",
};

const handRequirementLabels = {
  ONE_HAND: "uma mão",
  ONE_OR_TWO_HANDS: "uma ou duas mãos",
  TWO_HANDS: "duas mãos",
};

const toolCapabilityLabels = {
  HAMMERING: "martelar",
  CUTTING: "cortar",
  MINING: "minerar",
  SAWING: "serrar",
  COOKING: "cozinhar",
  FISHING: "pescar",
  SEWING: "costurar",
  LOCKPICKING: "abrir fechaduras",
};

const encumbranceLabels = {
  NORMAL: "Carga normal",
  LIGHTLY_ENCUMBERED: "Levemente sobrecarregado",
  HEAVILY_ENCUMBERED: "Muito sobrecarregado",
  OVERLOADED: "Carga excessiva",
};

function ItemCard({ item }: { item: InventoryItem }) {
  return (
    <article className="fantasy-content-card inventory-item-card">
      <div className="inventory-item-heading">
        <strong>{item.name}</strong>
        {item.quantity > 1 && <span className="inventory-item-qty">× {item.quantity}</span>}
      </div>

      <p className="inventory-item-meta">
        {formatWeight(item.total_weight)} de peso — qualidade {qualityLabels[item.quality]}
        {item.material && ` — material ${item.material.name}`}
        {item.contained_in_name && ` — dentro de ${item.contained_in_name}`}
        {item.container &&
          ` — recipiente ${formatWeight(item.container.content_weight)} / ${formatWeight(item.container.weight_capacity)} de peso`}
      </p>

      {item.signature_ornamentation && (
        <p className="inventory-item-ornamentation">{item.signature_ornamentation}</p>
      )}

      <div className="inventory-item-tags">
        {item.equipped_slot && (
          <span className="inventory-tag inventory-tag-slot">{equipmentSlotLabels[item.equipped_slot]}</span>
        )}
        <span className="inventory-tag">{accessibilityLabels[item.accessibility]}</span>
        {item.condition && (
          <StateBadge tone={conditionTone[item.condition]} label={conditionLabels[item.condition]} />
        )}
      </div>

      {item.weapon && (
        <p className="inventory-item-detail">
          {weaponFamilyLabels[item.weapon.family]} ·{" "}
          {item.weapon.damage_profiles.map((profile) => damageProfileLabels[profile]).join("/")} ·{" "}
          {weaponReachLabels[item.weapon.reach]} · {handRequirementLabels[item.weapon.hand_requirement]}
        </p>
      )}

      {item.armor && (
        <p className="inventory-item-detail">
          cobre {item.armor.coverage.map((area) => bodyAreaLabels[area]).join(", ")} · proteção{" "}
          {Object.entries(item.armor.physical_protections)
            .map(([profile, value]) => `${damageProfileLabels[profile as keyof typeof damageProfileLabels]} ${value}`)
            .join(", ")}
        </p>
      )}

      {item.tool && (
        <p className="inventory-item-detail">
          ferramenta para {item.tool.capabilities.map((capability) => toolCapabilityLabels[capability]).join(", ")}
        </p>
      )}
    </article>
  );
}

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

  const equipped = inventory.items.filter((item) => item.equipped);
  const bag = inventory.items.filter((item) => !item.equipped);

  return (
    <div className="inventory-panel">
      <p className="inventory-load-summary">
        Peso: {formatWeight(inventory.total_weight)} / {formatWeight(inventory.carrying_capacity)} —{" "}
        {encumbranceLabels[inventory.encumbrance]}
      </p>

      <section className="fantasy-section">
        <h4 className="fantasy-section-title">Equipado</h4>
        {equipped.length === 0 ? (
          <p className="panel-empty">Nada equipado.</p>
        ) : (
          <div className="inventory-item-grid">
            {equipped.map((item) => (
              <ItemCard key={item.item_instance_id} item={item} />
            ))}
          </div>
        )}
      </section>

      <section className="fantasy-section">
        <h4 className="fantasy-section-title">Mochila</h4>
        {bag.length === 0 ? (
          <p className="panel-empty">A mochila está vazia.</p>
        ) : (
          <div className="inventory-item-grid">
            {bag.map((item) => (
              <ItemCard key={item.item_instance_id} item={item} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
