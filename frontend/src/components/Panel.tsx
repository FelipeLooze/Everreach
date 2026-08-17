import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function Panel({ title, onClose, children }: PanelProps) {
  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="panel" onClick={(e) => e.stopPropagation()}>
        <div className="panel-header">
          <h2>{title}</h2>
          <button className="panel-close" onClick={onClose} aria-label="Fechar">
            ×
          </button>
        </div>
        <div className="panel-body">{children}</div>
      </div>
    </div>
  );
}
