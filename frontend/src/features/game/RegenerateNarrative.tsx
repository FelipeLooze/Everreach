import { useState } from "react";

interface RegenerateNarrativeProps {
  disabled: boolean;
  onRegenerate: (feedback: string) => Promise<boolean>;
}

export function RegenerateNarrative({ disabled, onRegenerate }: RegenerateNarrativeProps) {
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState("");

  const submit = async () => {
    const trimmed = feedback.trim();
    if (!trimmed || disabled) return;
    if (await onRegenerate(trimmed)) {
      setFeedback("");
      setOpen(false);
    }
  };

  if (!open) {
    return (
      <div className="regenerate-narrative-trigger">
        <button type="button" onClick={() => setOpen(true)} disabled={disabled}>
          Regenerar última mensagem
        </button>
      </div>
    );
  }

  return (
    <div className="regenerate-narrative-form">
      <label htmlFor="regeneration-feedback">O que deve mudar na última mensagem?</label>
      <textarea
        id="regeneration-feedback"
        value={feedback}
        maxLength={2000}
        disabled={disabled}
        placeholder="Ex.: deixe a resposta mais curta e não faça o NPC oferecer ajuda."
        onChange={(event) => setFeedback(event.target.value)}
      />
      <div>
        <button type="button" onClick={() => setOpen(false)} disabled={disabled}>
          Cancelar
        </button>
        <button type="button" onClick={submit} disabled={disabled || !feedback.trim()}>
          {disabled ? "Regenerando…" : "Regenerar"}
        </button>
      </div>
    </div>
  );
}
