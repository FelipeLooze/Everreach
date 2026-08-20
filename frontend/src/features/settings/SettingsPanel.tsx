import { useNavigate } from "react-router-dom";

export function SettingsPanel({ onExit }: { onExit: () => void }) {
  const navigate = useNavigate();

  const handleExit = () => {
    onExit();
    navigate("/", { replace: true });
  };

  return (
    <div className="settings-panel">
      <section className="fantasy-section">
        <h4 className="fantasy-section-title">Campanha</h4>
        <div className="settings-action-card">
          <div>
            <h5>Sair da campanha</h5>
            <p>Retorna ao menu inicial sem apagar a campanha, o personagem ou o histórico.</p>
          </div>
          <button className="exit-campaign-button" onClick={handleExit}>Sair</button>
        </div>
      </section>

      <div className="fantasy-divider" aria-hidden="true"><span /></div>

      <section className="fantasy-section settings-future-section">
        <h4 className="fantasy-section-title">Interface</h4>
        <p className="panel-empty">Mais opções de interface poderão ser adicionadas futuramente.</p>
      </section>
    </div>
  );
}
