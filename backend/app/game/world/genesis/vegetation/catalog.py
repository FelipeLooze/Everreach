"""One pinned v22 authority; compile once and discard the 59 MB source tree."""
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType

ROOT=Path(__file__).resolve().parents[6]
SOURCE="Everreach_Flora_3096_Extremos_Ecologia_v7_2.json"
SHA="a2d177f65e96ac90b572a6acc78c1513e9a01db40032257a3bbe3d58cf0acb38"


@dataclass(frozen=True)
class Species:
    id: str
    name: str
    kind: str
    habitats: tuple
    temperature: tuple | None
    rain: tuple | None
    aridity: tuple | None
    height_cm: tuple | None
    role: str
    rarity: int
    magic: str
    anomaly: str | None
    extreme_json: str | None
    stock: int | None
    parts_json: tuple
    rarity_name: str | None = None
    growth_json: str | None = None

    def parts(self):
        return [json.loads(p) for p in self.parts_json]


@dataclass(frozen=True)
class FloraCatalog:
    species: object
    by_habitat: object
    overlays_json: str
    source_hash: str
    contracts_json: str
    part_count: int
    item_count: int


@lru_cache(maxsize=1)
def load_flora_catalog():
    folder=ROOT/"datasets/02_Flora"
    raw=(folder/SOURCE).read_bytes()
    if sha256(raw).hexdigest()!=SHA:
        raise ValueError("Active flora v7.2 changed; an explicit importer version is required")
    data=json.loads(raw.decode("utf-8-sig"))
    index=json.loads((folder/"Everreach_Flora_Indice_3096_v7_2.json").read_text(encoding="utf-8-sig"))
    profiles={p["especie_id"]:p for p in data["perfis_ecologicos_world_genesis_v7_1"]}
    items={i["id"]:i for i in data["itens"]}
    species={};habitats={};parts_seen=set()
    for s in data["flora"]:
        p=profiles[s["id"]];f=p["criterios_fisicos"];a=p["afinidade_magica"]
        hs=tuple(dict.fromkeys(h for h in (p["habitat_preferencial_id"],*p["habitats_secundarios_ids"],*p["habitats_tolerados_ids"]) if h))
        parts=s["coleta"]["partes_coletaveis"]
        for part in parts:
            if part["id"] in parts_seen or items[part["item_id"]]["origem_flora_id"]!=s["id"]:
                raise ValueError("Duplicate part or mismatched canonical item")
            parts_seen.add(part["id"])
            if items[part["item_id"]]["nome"]!=part["item_nome"]:
                raise ValueError("Canonical item name mismatch")
        def interval(key):
            value=f.get(key)
            return tuple(value) if value is not None else None
        height=p["estrutura_vegetal"].get("altura_madura_cm_intervalo")
        record=Species(s["id"],s["nome"],s["tipo"],hs,interval("temperatura_media_anual_c_referencia"),
            interval("precipitacao_anual_mm_referencia"),interval("indice_aridez_referencia"),
            tuple(height) if height else None,p["estrutura_vegetal"]["papel_na_comunidade"],
            p["raridade_ecologica_0_100_nao_percentual"],a["classe"],a.get("anomalia_canonica_obrigatoria_id"),
            json.dumps(s["ecologia_extrema_v7_2"],ensure_ascii=False) if s.get("ecologia_extrema_v7_2") else None,
            s["ecologia"]["no_de_recurso"].get("estoque_por_no_sugerido"),
            tuple(json.dumps(part,ensure_ascii=False) for part in parts),s.get("raridade"),
            json.dumps(s.get("perfil_botanico_v7",{}).get("ciclo_de_vida_e_reproducao",{}),ensure_ascii=False))
        if record.id in species:raise ValueError("Duplicate species")
        species[record.id]=record
        for h in hs:habitats.setdefault(h,[]).append(record.id)
    if (len(species)!=3096 or len(profiles)!=3096 or len(parts_seen)!=6192 or len(items)!=6192 or
            index["total_especies"]!=len(species) or set(index["novas_ids"])!={f"EV-FL-{i:04d}" for i in range(3001,3097)}):
        raise ValueError("v22 cardinality/index mismatch")
    # Indexes never authorize an occurrence; overlays remain conditional, separate records.
    overlays=data["extensoes_de_habitat_legado_v7_2"]
    if len(overlays)!=8:raise ValueError("v22 conditional overlay mismatch")
    contracts={k:data[k] for k in ("contrato_world_genesis_v7_1","regras_extremos_v7_2","modelo_ecologico_e_coleta_v7")}
    return FloraCatalog(MappingProxyType(species),MappingProxyType({k:tuple(v) for k,v in habitats.items()}),
        json.dumps(overlays,ensure_ascii=False),SHA,json.dumps(contracts,ensure_ascii=False),len(parts_seen),len(items))
