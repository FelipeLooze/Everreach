"""Bounded regional mosaics of canonical point classifications, never uniform biomes."""
from collections import Counter


def summarize_environment(samples):
    samples=list(samples)
    if len(samples)>256:
        raise ValueError("E1 mosaic budget is 256 physical samples per request")
    unique={s["probe_id"]:s for s in samples}
    signatures={s["authority_signature"] for s in unique.values()}
    if len(signatures)>1:
        raise ValueError("Cannot combine different environmental authorities")
    ordered=[unique[k] for k in sorted(unique)]
    covers=Counter(s["primary_potential"] for s in ordered if s["primary_potential"])
    return {"kind":"regional_environment_mosaic_e1","environment_version":1,"sample_count":len(ordered),
        "duplicate_samples_ignored":len(samples)-len(ordered),"authority_signature":next(iter(signatures),None),
        "macro_climate_cells":sorted({tuple(s["hierarchy"]["macro_climate_cell"]) for s in ordered}),
        "regional_formation_ids":sorted({s["hierarchy"]["regional_formation_id"] for s in ordered}),
        "primary_potential_counts":dict(sorted(covers.items())),"primary_diversity":len(covers),
        "local_features":dict(Counter(e for s in ordered for e in s["feature_layers"])),
        "ecotone_probe_ids":[s["probe_id"] for s in ordered if s["ecotone"]],
        "coverage":"sampled_mosaic_not_uniform_continent_or_render_LOD","vegetation_established":None,
        "population_spawn_authorized":False}
