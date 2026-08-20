import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  size?: "default" | "wide";
}

export function Panel({ title, onClose, children, size = "default" }: PanelProps) {
  return (
    <div className="panel-overlay" onClick={onClose}>
      <div
        className={`panel ${size === "wide" ? "panel-wide" : ""}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="panel-title"
      >
        <div className="panel-header">
          <div className="panel-title-ornament" aria-hidden="true"><span /></div>
          <h2 id="panel-title">{title}</h2>
          <div className="panel-title-ornament panel-title-ornament-right" aria-hidden="true"><span /></div>
          <button className="panel-close" onClick={onClose} aria-label="Fechar">
            ×
          </button>
        </div>
        <div className="panel-body">{children}</div>
      </div>
    </div>
  );
}
