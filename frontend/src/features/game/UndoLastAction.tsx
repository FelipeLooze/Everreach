import { useState } from "react";

interface UndoLastActionProps {
  actionText: string;
  disabled: boolean;
  onUndo: (reason: string) => Promise<boolean>;
}

export function UndoLastAction({ actionText, disabled, onUndo }: UndoLastActionProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");

  const submit = async () => {
    const trimmed = reason.trim();
    if (!trimmed || disabled) return;
    if (await onUndo(trimmed)) {
      setReason("");
      setOpen(false);
    }
  };

  if (!open) {
    return (
      <button type="button" className="undo-last-action-button" onClick={() => setOpen(true)} disabled={disabled}>
        Desfazer última ação
      </button>
    );
  }

  return (
    <div className="undo-last-action-form">
      <strong>Desfazer: “{actionText}”?</strong>
      <p>
        O jogo restaurará o estado anterior, incluindo inventário, recursos, localização,
        relógio e combate. A ação não será executada novamente.
      </p>
      <label htmlFor="undo-reason">Por que esta ação deve ser desfeita?</label>
      <textarea
        id="undo-reason"
        value={reason}
        maxLength={1000}
        disabled={disabled}
        placeholder="Ex.: o item não deveria ter saído do inventário."
        onChange={(event) => setReason(event.target.value)}
      />
      <div>
        <button type="button" onClick={() => setOpen(false)} disabled={disabled}>
          Cancelar
        </button>
        <button type="button" className="danger" onClick={submit} disabled={disabled || !reason.trim()}>
          {disabled ? "Desfazendo…" : "Confirmar desfazer"}
        </button>
      </div>
    </div>
  );
}
