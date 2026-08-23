/**
 * Phase 21L — Visual State & Condition Representation.
 *
 * ONE shared, reusable way for the UI to express world/entity state
 * visually — an item damaged, an NPC injured, a route reported
 * blocked, a location destroyed, an organization relationship hostile.
 * StateBadge never changes or invents mechanics; it only presents
 * whatever tone/label a caller already derived from real backend
 * state (see app.game.items.durability.get_item_condition and
 * similar, backend-side, Phase 21 modules — this component receives
 * the result, it never decides it).
 *
 * "NO COLOR-ONLY SEMANTICS" (spec, mandatory): every tone pairs a
 * distinct border STYLE (solid/dashed/dotted/double) with its color,
 * plus a small glyph — never color alone. A reader with color-vision
 * deficiency, or a screenshot rendered in grayscale, can still tell
 * tones apart.
 */
export type StateTone = "danger" | "warning" | "success" | "uncertain" | "unknown" | "neutral";

const TONE_GLYPHS: Record<StateTone, string> = {
  danger: "⚠",
  warning: "!",
  success: "✓",
  uncertain: "?",
  unknown: "?",
  neutral: "•",
};

export function StateBadge({
  tone,
  label,
}: {
  tone: StateTone;
  label: string;
}) {
  return (
    <span className={`state-badge state-badge-${tone}`}>
      <span className="state-badge-glyph" aria-hidden="true">
        {TONE_GLYPHS[tone]}
      </span>
      <span className="state-badge-label">{label}</span>
    </span>
  );
}
