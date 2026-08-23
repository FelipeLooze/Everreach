/**
 * Phase 21Q — Future Generated-Asset Compatibility.
 *
 * ONE shared, reusable slot for a future generated visual asset
 * (an NPC portrait, an item illustration, ...). `assetUrl` is
 * whatever a future generation pipeline eventually produces — this
 * component never builds one, never assumes a ComfyUI path shape,
 * and is expected to render `null`/`undefined` for the overwhelming
 * majority of entities today ("no dependency on ComfyUI", spec,
 * mandatory).
 *
 * "Every visual component must work without a generated image"
 * (spec, mandatory): absent an assetUrl, this renders an elegant
 * glyph placeholder rather than an empty box, so the slot itself is
 * always a legible piece of UI.
 */
export function AssetSlot({
  assetUrl,
  placeholderGlyph,
  label,
}: {
  assetUrl?: string | null;
  placeholderGlyph: string;
  label: string;
}) {
  if (assetUrl) {
    return <img className="asset-slot asset-slot-image" src={assetUrl} alt={label} />;
  }
  return (
    <div className="asset-slot asset-slot-placeholder" role="img" aria-label={label}>
      <span aria-hidden="true">{placeholderGlyph}</span>
    </div>
  );
}
