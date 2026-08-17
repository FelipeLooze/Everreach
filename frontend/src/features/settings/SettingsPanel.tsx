import { useNavigate } from "react-router-dom";

export function SettingsPanel({ onExit }: { onExit: () => void }) {
  const navigate = useNavigate();

  const handleExit = () => {
    onExit();
    navigate("/", { replace: true });
  };

  return (
    <div className="settings-panel">
      <h4>Sair da campanha</h4>
      <p>Retorna ao menu inicial sem apagar a campanha, o personagem ou o histórico.</p>
      <button onClick={handleExit}>Sair</button>
    </div>
  );
}
