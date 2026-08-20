import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createCampaign,
  createCharacter,
  deleteCampaign,
  listCampaigns,
} from "@/api/campaigns";
import type { EarthProfession } from "@/api/campaigns";
import { useGameStore } from "@/stores/useGameStore";
import type { CampaignWithCharacters, Character } from "@/types/game";

export function CampaignSetupPage() {
  const navigate = useNavigate();
  const setSession = useGameStore((state) => state.setSession);
  const [menu, setMenu] = useState<"main" | "play" | "create" | "campaigns" | "settings">("main");
  const [campaignName, setCampaignName] = useState("");
  const [characterName, setCharacterName] = useState("");
  const [earthProfession, setEarthProfession] = useState<EarthProfession | "">("");
  const [campaigns, setCampaigns] = useState<CampaignWithCharacters[]>([]);
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);
  const [busy, setBusy] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshCampaigns = async () => {
    setLoadingCampaigns(true);
    try {
      setCampaigns(await listCampaigns());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível carregar as campanhas.");
    } finally {
      setLoadingCampaigns(false);
    }
  };

  useEffect(() => {
    void refreshCampaigns();
  }, []);

  const handleCreate = async () => {
    if (!campaignName.trim() || !characterName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const campaign = await createCampaign(campaignName.trim());
      const character = await createCharacter(
        campaign.id,
        characterName.trim(),
        earthProfession || null,
      );
      setSession(campaign.id, character.id);
      navigate("/game");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível criar a campanha.");
      await refreshCampaigns();
    } finally {
      setBusy(false);
    }
  };

  const handleContinue = (campaignId: string, character: Character) => {
    setSession(campaignId, character.id);
    navigate("/game");
  };

  const handleDelete = async (campaign: CampaignWithCharacters) => {
    if (!window.confirm(`Excluir permanentemente a campanha “${campaign.name}” e todo o seu histórico?`)) {
      return;
    }
    setDeletingId(campaign.id);
    setError(null);
    try {
      await deleteCampaign(campaign.id);
      setCampaigns((current) => current.filter((item) => item.id !== campaign.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível excluir a campanha.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
  <div className="menu-background">
    <div className="main-menu">
      <header className="game-logo">
        <h1>EVERREACH</h1>
        <span>MUNDO VIVO</span>
      </header>

      {menu === "main" && (
        <nav className="main-menu-options">
          <button onClick={() => setMenu("play")}>
            JOGAR
          </button>

          <button onClick={() => setMenu("create")}>
            CRIAR PERSONAGEM
          </button>

          <button onClick={() => setMenu("campaigns")}>
            CAMPANHAS
          </button>

          <button onClick={() => setMenu("settings")}>
            CONFIGURAÇÕES
          </button>
        </nav>
      )}

      {menu === "create" && (
        <section className="menu-panel">
          <button
            className="menu-back"
            onClick={() => setMenu("main")}
          >
            ← Voltar
          </button>

          <h2>Nova jornada</h2>

          <label>
            Nome da campanha
            <input
              value={campaignName}
              onChange={(event) => setCampaignName(event.target.value)}
              disabled={busy}
            />
          </label>

          <label>
            Nome do personagem
            <input
              value={characterName}
              onChange={(event) => setCharacterName(event.target.value)}
              disabled={busy}
            />
          </label>

          <label htmlFor="earth-profession">
            Experiência profissional na Terra
          </label>
          <select
            id="earth-profession"
            value={earthProfession}
            onChange={(event) =>
              setEarthProfession(event.target.value as EarthProfession | "")
            }
            disabled={busy}
          >
            <option value="">Nenhuma afinidade profissional</option>
            <option value="CHEF">Chef profissional — Culinária</option>
            <option value="FARMER">Agricultor — Agricultura</option>
            <option value="CARPENTER">Carpinteiro — Carpintaria</option>
            <option value="BLACKSMITH">Ferreiro — Ferraria</option>
          </select>
          <small>
            Concede somente +10% de XP na profissão correspondente; não concede níveis.
          </small>

          <button
            className="primary-menu-button"
            onClick={handleCreate}
            disabled={
              busy ||
              !campaignName.trim() ||
              !characterName.trim()
            }
          >
            {busy ? "Criando…" : "CRIAR PERSONAGEM"}
          </button>
        </section>
      )}

      {menu === "campaigns" && (
        <section className="menu-panel">
          <button
            className="menu-back"
            onClick={() => setMenu("main")}
          >
            ← Voltar
          </button>

          <h2>Campanhas</h2>

          {loadingCampaigns && <p>Carregando...</p>}

          {campaigns.map((campaign) => (
            <article className="menu-campaign" key={campaign.id}>
              <div className="campaign-card-header">
                <div>
                  <h3>{campaign.name}</h3>

                  <small>
                    Criada em{" "}
                    {new Date(campaign.created_at).toLocaleDateString("pt-BR")}
                  </small>
                </div>

                <button
                  className="danger-button"
                  onClick={() => void handleDelete(campaign)}
                  disabled={deletingId === campaign.id}
                >
                  {deletingId === campaign.id ? "Excluindo…" : "Excluir"}
                </button>
              </div>

              {campaign.characters.length === 0 && (
                <p className="panel-empty">
                  Esta campanha não possui personagem.
                </p>
              )}

              {campaign.characters.map((character) => (
                <div className="menu-character" key={character.id}>
                  <span>
                    <strong>{character.name}</strong>
                    <small>Level {character.level}</small>

                    {character.status === "DEAD" && (
                      <small className="char-dead">Morto</small>
                    )}
                    {character.status === "INCAPACITATED" && (
                      <small className="char-incapacitated">Incapacitado</small>
                    )}
                  </span>

                  <button
                    onClick={() =>
                      handleContinue(campaign.id, character)
                    }
                  >
                    JOGAR
                  </button>
                </div>
              ))}
            </article>
          ))}
        </section>
      )}

      {menu === "play" && (
        <section className="menu-panel">
          <button
            className="menu-back"
            onClick={() => setMenu("main")}
          >
            ← Voltar
          </button>

          <h2>Continuar jornada</h2>

          {campaigns.flatMap((campaign) =>
            campaign.characters.map((character) => (
              <button
                className="continue-card"
                key={character.id}
                onClick={() =>
                  handleContinue(
                    campaign.id,
                    character
                  )
                }
              >
                <strong>{character.name}</strong>

                <span>{campaign.name}</span>

                <small>
                  Level {character.level}
                </small>
              </button>
            ))
          )}
        </section>
      )}

      {menu === "settings" && (
        <section className="menu-panel">
          <button
            className="menu-back"
            onClick={() => setMenu("main")}
          >
            ← Voltar
          </button>

          <h2>Configurações</h2>

          <p>Configurações serão adicionadas aqui.</p>
        </section>
      )}

      {error && (
        <p className="panel-error">{error}</p>
      )}
    </div>
  </div>
);
}
