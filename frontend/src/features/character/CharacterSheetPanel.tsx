import { useCallback, useEffect, useState } from "react";
import {
  acceptClassOffer,
  delayClassOffer,
  getCharacterSheet,
} from "@/api/character";
import type { CharacterSheet } from "@/types/game";
import { characterAttributeLabel } from "@/utils/labels";

export function CharacterSheetPanel({ campaignId, characterId }: { campaignId: string; characterId: string }) {
  const [sheet, setSheet] = useState<CharacterSheet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyOfferId, setBusyOfferId] = useState<string | null>(null);

  const loadSheet = useCallback(() =>
    getCharacterSheet(campaignId, characterId)
      .then(setSheet)
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Falha ao carregar o personagem.");
      }), [campaignId, characterId]);

  useEffect(() => {
    void loadSheet();
  }, [loadSheet]);

  const chooseClass = async (offerId: string, choice: "accept" | "delay") => {
    setBusyOfferId(offerId);
    setError(null);
    try {
      if (choice === "accept") {
        await acceptClassOffer(campaignId, characterId, offerId);
      } else {
        await delayClassOffer(campaignId, characterId, offerId);
      }
      await loadSheet();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao escolher a classe.");
    } finally {
      setBusyOfferId(null);
    }
  };

  if (error) return <p className="panel-error">{error}</p>;
  if (!sheet) return <p>Carregando…</p>;

  return (
    <div>
      <h3>{sheet.character.name} — Nível {sheet.character.level}</h3>
      <p>XP: {sheet.character.xp.toFixed(1)}</p>
      {sheet.character.background && (
        <p>Experiência na Terra: {sheet.character.background}</p>
      )}

      <h4>Classe</h4>
      {sheet.active_class ? (
        <div>
          <strong>{sheet.active_class.name}</strong>
          <p>{sheet.active_class.description}</p>
        </div>
      ) : (
        <p className="panel-empty">Nenhuma classe ativa.</p>
      )}

      {sheet.class_offers.length > 0 && (
        <div>
          <h5>Classes disponíveis</h5>
          <ul>
            {sheet.class_offers.map((offer) => (
              <li key={offer.id}>
                <strong>{offer.class_definition.name}</strong>
                <p>{offer.class_definition.description}</p>
                {offer.status === "DELAYED" && <small>Oferta adiada.</small>}
                <div>
                  <button
                    type="button"
                    disabled={busyOfferId === offer.id}
                    onClick={() => void chooseClass(offer.id, "accept")}
                  >
                    ACEITAR
                  </button>
                  {offer.status === "AVAILABLE" && (
                    <button
                      type="button"
                      disabled={busyOfferId === offer.id}
                      onClick={() => void chooseClass(offer.id, "delay")}
                    >
                      ADIAR
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <h4>Profissões</h4>
      {sheet.professions.length === 0 ? (
        <p className="panel-empty">Nenhuma profissão desenvolvida ainda.</p>
      ) : (
        <ul>
          {sheet.professions.map((profession) => (
            <li key={profession.key}>
              {profession.name}: Level {profession.level} — {profession.xp.toFixed(1)} XP
            </li>
          ))}
        </ul>
      )}

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
