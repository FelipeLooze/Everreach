import { useEffect, useState } from "react";
import { getCharacterSheet } from "@/api/character";
import type { CharacterSheet } from "@/types/game";
import { characterAttributeLabel } from "@/utils/labels";

export function CharacterSheetPanel({ campaignId, characterId }: { campaignId: string; characterId: string }) {
  const [sheet, setSheet] = useState<CharacterSheet | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCharacterSheet(campaignId, characterId)
      .then(setSheet)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar o personagem."));
  }, [campaignId, characterId]);

  if (error) return <p className="panel-error">{error}</p>;
  if (!sheet) return <p>Carregando…</p>;

  return (
    <div>
      <h3>{sheet.character.name} — Nível {sheet.character.level}</h3>
      <p>XP: {sheet.character.xp.toFixed(1)}</p>

      <h4>Atributos</h4>
      {sheet.attributes.length === 0 ? (
        <p className="panel-empty">Nenhum atributo registrado.</p>
      ) : (
        <ul>
          {sheet.attributes.map((a) => (
            <li key={a.name}>
              {characterAttributeLabel(a.name)}: {a.value}
            </li>
          ))}
        </ul>
      )}

      <h4>Perícias</h4>
      {sheet.skills.length === 0 ? (
        <p className="panel-empty">Nenhuma perícia aprendida ainda.</p>
      ) : (
        <ul>
          {sheet.skills.map((s) => (
            <li key={s.name}>
              {s.name}: domínio {s.mastery.toFixed(1)}
            </li>
          ))}
        </ul>
      )}

      <h4>Técnicas</h4>
      {sheet.techniques.length === 0 ? (
        <p className="panel-empty">Nenhuma técnica descoberta ainda.</p>
      ) : (
        <ul>
          {sheet.techniques.map((t) => (
            <li key={t.name}>
              <strong>{t.name}</strong> — {t.description}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
