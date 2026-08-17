import { useState } from "react";

interface ActionInputProps {
  onSubmit: (text: string) => void;
  disabled: boolean;
}

export function ActionInput({ onSubmit, disabled }: ActionInputProps) {
  const [text, setText] = useState("");

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setText("");
  };

  return (
    <div className="action-input">
      <input
        type="text"
        value={text}
        disabled={disabled}
        placeholder={disabled ? "O personagem não pode mais agir." : "O que você deseja fazer?"}
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
