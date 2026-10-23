import { useCallback, useEffect, useState } from "react";
import { getEconomy } from "@/api/economy";
import type { EconomyState } from "@/types/game";

type EconomyPanelProps = {
  campaignId: string;
  characterId: string;
  onAction: (text: string) => Promise<unknown>;
};

const duration = (minutes: number) => {
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (!hours) return `${remainder} min`;
  return remainder ? `${hours} h ${remainder} min` : `${hours} h`;
};

export function EconomyPanel({ campaignId, characterId, onAction }: EconomyPanelProps) {
  const [economy, setEconomy] = useState<EconomyState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setEconomy(await getEconomy(campaignId, characterId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar a economia local.");
    }
  }, [campaignId, characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (key: string, command: string) => {
    setPending(key);
    setError(null);
    try {
      await onAction(command);
      await load();
    } finally {
      setPending(null);
    }
  };

  if (!economy) return error ? <p className="panel-error">{error}</p> : <p>Carregando…</p>;

  const empty = economy.shops.length === 0 && economy.jobs.length === 0 && economy.recipes.length === 0;

  return (
    <div className="economy-panel">
      <header className="economy-summary">
        <div><span>Saldo carregado</span><strong>{economy.balance_bronze} Bronze</strong></div>
        <div><span>Local</span><strong>{economy.location_name ?? "Desconhecido"}</strong></div>
      </header>
      <p className="economy-note">Dinheiro, estoque e fundos dos estabelecimentos são finitos. Toda operação acontece como uma ação do personagem e pode ser desfeita pelo checkpoint da última ação.</p>
      {error && <p className="panel-error">{error}</p>}
      {empty && <p className="panel-empty">Não há comércio, trabalho ou oficina acessível neste local.</p>}

      {economy.shops.map((shop) => (
        <section className="economy-section" key={shop.shop_id}>
          <h3>{shop.name}</h3>
          {!shop.operator_available && <p className="economy-unavailable">O responsável não está disponível agora.</p>}
          {shop.listings.length > 0 && <h4>Comprar</h4>}
          <div className="economy-grid">
            {shop.listings.map((listing) => (
              <article className="economy-card" key={listing.listing_id}>
                <div><strong>{listing.name}</strong><span>{listing.quantity} em estoque</span></div>
                <button
                  disabled={!shop.operator_available || pending !== null}
                  onClick={() => void act(`buy:${listing.listing_id}`, `Compro "${listing.name}" em "${shop.name}"`)}
                >
                  {pending === `buy:${listing.listing_id}` ? "Comprando…" : `${listing.unit_price_bronze} Bronze`}
                </button>
              </article>
            ))}
          </div>
          {shop.sellable_items.length > 0 && <h4>Vender</h4>}
          <div className="economy-grid">
            {shop.sellable_items.map((item) => (
              <article className="economy-card" key={item.item_instance_id}>
                <div><strong>{item.name}</strong><span>{item.quantity} unidade(s)</span></div>
                <button
                  disabled={!shop.operator_available || pending !== null}
                  onClick={() => void act(`sell:${item.item_instance_id}`, `Vendo "${item.name}" para "${shop.name}"`)}
                >
                  {pending === `sell:${item.item_instance_id}` ? "Vendendo…" : `Receber ${item.price_bronze}`}
                </button>
              </article>
            ))}
          </div>
        </section>
      ))}

      {economy.jobs.length > 0 && (
        <section className="economy-section">
          <h3>Trabalho</h3>
          <div className="economy-grid">
            {economy.jobs.map((job) => {
              const employed = job.application_status === "ACTIVE";
              const command = employed
                ? `Trabalho no emprego "${job.title}"`
                : `Candidato-me ao trabalho "${job.title}"`;
              return (
                <article className="economy-card economy-job" key={job.job_id}>
                  <div>
                    <strong>{job.title}</strong>
                    <span>{job.employer_name}</span>
                    <p>{job.description}</p>
                    <small>{job.wage_bronze} Bronze por turno · {duration(job.work_minutes)} · Horário: {job.schedule}</small>
                  </div>
                  <div className="economy-actions">
                    <button
                      disabled={!job.employer_available || pending !== null}
                      onClick={() => void act(`job:${job.job_id}`, command)}
                    >
                      {pending === `job:${job.job_id}` ? "Processando…" : employed ? "Cumprir turno" : "Candidatar-se"}
                    </button>
                    {employed && (
                      <button
                        className="economy-secondary-action"
                        disabled={pending !== null}
                        onClick={() => void act(`leave-job:${job.job_id}`, `Deixo o emprego "${job.title}"`)}
                      >
                        Sair do emprego
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      )}

      {economy.recipes.length > 0 && (
        <section className="economy-section">
          <h3>Produção</h3>
          <div className="economy-grid">
            {economy.recipes.map((recipe) => (
              <article className="economy-card economy-recipe" key={recipe.key}>
                <div>
                  <strong>{recipe.name}</strong>
                  <p>{recipe.description}</p>
                  <span>Usa: {recipe.inputs.map((item) => `${item.quantity}× ${item.name}`).join(", ")}</span>
                  <span>Produz: {recipe.outputs.map((item) => `${item.quantity}× ${item.name}`).join(", ")}</span>
                  {recipe.missing.length > 0 && <small>Falta: {recipe.missing.join(", ")}</small>}
                </div>
                <button
                  disabled={!recipe.can_produce || pending !== null}
                  onClick={() => void act(`recipe:${recipe.key}`, `Produzo "${recipe.name}"`)}
                >
                  {pending === `recipe:${recipe.key}` ? "Produzindo…" : `Produzir · ${duration(recipe.minutes)}`}
                </button>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
