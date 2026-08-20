import { useState } from "react";
import type { CharacterTechnique } from "@/types/game";

interface ActionInputProps {
  onSubmit: (text: string, techniqueId?: string) => void;
  disabled: boolean;
  techniques: CharacterTechnique[];
}

export function ActionInput({ onSubmit, disabled, techniques }: ActionInputProps) {
  const [text, setText] = useState("");
  const [techniqueId, setTechniqueId] = useState("");

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed, techniqueId || undefined);
    setText("");
  };

  return (
    <div className="action-input">
      {techniques.length > 0 && (
        <select
          aria-label="Técnica usada"
          value={techniqueId}
          disabled={disabled}
          onChange={(event) => setTechniqueId(event.target.value)}
        >
          <option value="">Ação livre</option>
          {techniques.map((technique) => (
            <option key={technique.id} value={technique.id}>
              {technique.name}
            </option>
          ))}
        </select>
      )}
      <input
        type="text"
        value={text}
        disabled={disabled}
        placeholder={
          disabled
            ? "O personagem não pode mais agir."
            : techniqueId
              ? "Como você usa esta técnica?"
              : "O que você deseja fazer?"
        }
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
        }}
      />
      <button onClick={submit} disabled={disabled || !text.trim()}>
        Agir
      </button>
    </div>
  );
}
