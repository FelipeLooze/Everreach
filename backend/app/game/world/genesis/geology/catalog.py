"""Load only active D14 files; no legacy catalog remapping or runtime editing."""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
BASE_SHA256 = "1101b05722d85fdc9168d0ed6117e1a3c960343d40a992ada6417e86d92a7eec"


@lru_cache(maxsize=1)
def _load():
    base = ROOT/"datasets/11_Geologia_Materiais_D14/Everreach_Dataset14_Materiais_Fantasia_120_Ocorrencia_v4.json"
    extension = ROOT/"datasets/11_Geologia_Materiais_D14_Complemento_v4_1/Everreach_Dataset14_Complemento_Geologico_4_1.json"
    raw, extra = base.read_bytes(), extension.read_bytes()
    if sha256(raw).hexdigest() != BASE_SHA256:
        raise ValueError("D14 v4 immutable catalog checksum mismatch")
    v4, v41 = json.loads(raw.decode("utf-8-sig")), json.loads(extra.decode("utf-8-sig"))
    materials = {m["id"]: m for m in v4["materiais_fantasticos"]}
    substrates = {s["id"]: s for s in v41["rochas_e_substratos"]}
    bridges = {b["modelo_ocorrencia_v4_id"]: b for b in v41["pontes_modelos_ocorrencia_v4_t1"]}
    alternatives = v41["rotas_alternativas_por_material"]
    if (len(materials) != 120 or len(substrates) != 20 or len(bridges) != 18 or len(alternatives) != 24 or
            sum(len(m["extracao_e_obtencao"]["perfis_por_contexto"]) for m in materials.values()) != 360 or
            any(len(m["propriedades_0_100"]) != 14 for m in materials.values())):
        raise ValueError("D14 catalog cardinality mismatch")
    for material in materials.values():
        if material["origem_condicional"]["modelo_geologico"] not in bridges:
            raise ValueError("Missing primary occurrence bridge")
    for alternative in alternatives:
        if (alternative["material_id"] not in materials or alternative["origem_alternativa_modelo_id"] not in bridges or
                alternative["origem_principal_v4_preservada"] != materials[alternative["material_id"]]["origem_condicional"]["modelo_geologico"]):
            raise ValueError("Invalid additive occurrence route")
    return {"base_sha256": BASE_SHA256, "extension_sha256": sha256(extra).hexdigest(),
            "materials": materials, "substrates": substrates, "bridges": bridges, "alternatives": alternatives}


def load_catalog():
    return deepcopy(_load())  # callers cannot mutate cached authority
