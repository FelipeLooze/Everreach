import { useEffect, useState } from "react";
import { getInventory } from "@/api/inventory";
import type { Inventory } from "@/types/game";

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
            <li key={item.item_instance_id}>
              {item.name} ({item.type}) × {item.quantity} — {formatWeight(item.total_weight)} de peso
              {` — qualidade ${qualityLabels[item.quality]}`}
              {item.equipped_slot && ` — ${equipmentSlotLabels[item.equipped_slot]}`}
              {` — ${accessibilityLabels[item.accessibility]}`}
              {item.weapon && (
                <small>
                  {` — ${weaponFamilyLabels[item.weapon.family]}; ${item.weapon.damage_profiles.map((profile) => damageProfileLabels[profile]).join("/")}; ${weaponReachLabels[item.weapon.reach]}; ${handRequirementLabels[item.weapon.hand_requirement]}`}
                </small>
              )}
              {item.armor && (
                <small>
                  {` — cobre ${item.armor.coverage.map((area) => bodyAreaLabels[area]).join(", ")}; proteção ${Object.entries(item.armor.physical_protections).map(([profile, value]) => `${damageProfileLabels[profile as keyof typeof damageProfileLabels]} ${value}`).join(", ")}`}
                </small>
              )}
              {item.tool && (
                <small>
                  {` — ferramenta para ${item.tool.capabilities.map((capability) => toolCapabilityLabels[capability]).join(", ")}`}
                </small>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
