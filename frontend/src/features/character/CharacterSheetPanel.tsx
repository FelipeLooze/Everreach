import { useCallback, useEffect, useState } from "react";
import {
  acceptClassOffer,
  delayClassOffer,
  getCharacterSheet,
} from "@/api/character";
import type { CharacterSheet } from "@/types/game";
import {
  characterAttributeLabel,
  techniqueMasteryLabel,
  techniqueTypeLabel,
} from "@/utils/labels";

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
    <div className="character-sheet">
      <header className="character-sheet-summary">
        <div className="character-emblem" aria-hidden="true"><span>ER</span></div>
        <div className="character-summary-copy">
          <span className="fantasy-eyebrow">FICHA DO PERSONAGEM</span>
          <h3>{sheet.character.name}</h3>
          {sheet.character.background && (
            <p>Experiência na Terra: {sheet.character.background}</p>
          )}
          <div className="character-xp-line">
            <span>XP: {sheet.character.xp.toFixed(1)}</span>
            <span className="character-xp-rule" />
          </div>
        </div>
        <div className="character-level-badge">
          <span>NÍVEL</span>
          <strong>{sheet.character.level}</strong>
        </div>
      </header>

      <div className="fantasy-divider" aria-hidden="true"><span /></div>

      <div className="character-sheet-layout">
        <div className="character-info-column">
          <section className="fantasy-section">
            <h4 className="fantasy-section-title">Classe</h4>
            {sheet.active_class ? (
              <div className="fantasy-content-card class-card">
                <strong>{sheet.active_class.name}</strong>
                <p>{sheet.active_class.description}</p>
              </div>
            ) : (
              <p className="panel-empty">Nenhuma classe ativa.</p>
            )}

            {sheet.class_offers.length > 0 && (
              <div className="class-offers">
                <h5>Classes disponíveis</h5>
                {sheet.class_offers.map((offer) => (
                  <article className="fantasy-content-card class-offer-card" key={offer.id}>
                    <strong>{offer.class_definition.name}</strong>
                    <p>{offer.class_definition.description}</p>
                    {offer.status === "DELAYED" && <small>Oferta adiada.</small>}
                    <div className="class-offer-actions">
                      <button type="button" disabled={busyOfferId === offer.id} onClick={() => void chooseClass(offer.id, "accept")}>ACEITAR</button>
                      {offer.status === "AVAILABLE" && (
                        <button type="button" disabled={busyOfferId === offer.id} onClick={() => void chooseClass(offer.id, "delay")}>ADIAR</button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="fantasy-section">
            <h4 className="fantasy-section-title">Profissões</h4>
            {sheet.professions.length === 0 ? (
              <p className="panel-empty">Nenhuma profissão desenvolvida ainda.</p>
            ) : (
              <div className="compact-card-list">
                {sheet.professions.map((profession) => (
                  <p className="fantasy-content-card" key={profession.key}>
                    {profession.name}: Level {profession.level} — {profession.xp.toFixed(1)} XP
                  </p>
                ))}
              </div>
            )}
          </section>

          <section className="fantasy-section">
            <h4 className="fantasy-section-title">Perícias</h4>
            {sheet.skills.length === 0 ? (
              <p className="panel-empty">Nenhuma perícia aprendida ainda.</p>
            ) : (
              <div className="compact-card-list">
                {sheet.skills.map((skill) => (
                  <p className="fantasy-content-card" key={skill.name}>
                    {skill.name}: domínio {skill.mastery.toFixed(1)}
                  </p>
                ))}
              </div>
            )}
          </section>
        </div>

        <section className="fantasy-section character-attributes-section">
          <h4 className="fantasy-section-title">Atributos</h4>
          {sheet.attributes.length === 0 ? (
            <p className="panel-empty">Nenhum atributo registrado.</p>
          ) : (
            <div className="attribute-grid">
              {sheet.attributes.map((attribute) => (
                <article className="attribute-card" key={attribute.key}>
                  <span>{characterAttributeLabel(attribute.key)}</span>
                  <strong>{attribute.value}</strong>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="fantasy-section techniques-section">
        <h4 className="fantasy-section-title">Técnicas</h4>
        {sheet.techniques.length === 0 ? (
          <p className="panel-empty">Nenhuma técnica descoberta ainda.</p>
        ) : (
          <div className="technique-grid">
            {sheet.techniques.map((technique) => (
              <article className="fantasy-content-card technique-card" key={technique.name}>
                <strong>{technique.name}</strong>
                <span className="technique-meta">
                  {techniqueTypeLabel(technique.type)} · maestria {techniqueMasteryLabel(technique.mastery)}
                </span>
                <p>{technique.description}</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
