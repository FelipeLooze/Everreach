"""One pinned EV-ECO entry from the active package; historical rules are not inputs."""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[6]
FILES={
    "taxonomy":("Everreach_Taxonomia_250_Ambientes_EV_ECO_1_1.json","f3cfedee7e4196e71f796555e1cecf5ff69d7f0a464e124fb5f0f803808056d7"),
    "index":("Everreach_EV_ECO_1_1_Indice_250.json","902ced64324b603aa8f51781769946708fee167399144049ad25360fa23c9d6f"),
    "rules":("Everreach_EV_ECO_1_1_1_Regras_Fisicas_250.json","4eb814c21fec195536d43caf419b8b9ff8876bbdaf516461dcf53f9561653005")}


@lru_cache(maxsize=1)
def _load():
    folder=ROOT/"datasets/00_Taxonomia_Ambientes"
    manifest=json.loads((folder/"manifesto_ambiental_ativo.json").read_text(encoding="utf-8-sig"))
    if manifest["dataset"]!="EV-ECO-1.1.1" or manifest["pasta_ativa"]!="00_Taxonomia_Ambientes/":
        raise ValueError("Active environmental entry mismatch")
    data={}
    for key,(name,digest) in FILES.items():
        raw=(folder/name).read_bytes()
        if sha256(raw).hexdigest()!=digest:
            raise ValueError("Pinned EV-ECO-1.1.1 catalog changed")
        data[key]=json.loads(raw.decode("utf-8-sig"))
    t,r=data["taxonomy"],data["rules"]
    natural={x["id"]:x for x in t["biomas_ecossistemas_naturais"]}
    built={x["ambiente_id"]:x for x in r["camadas_construidas"]}
    anomalies={x["ambiente_id"]:x for x in r["camadas_anomalas"]}
    rules={x["ambiente_id"]:x for x in r["ambientes_naturais"]}
    ids=set(natural)|set(built)|set(anomalies)
    if (r["schema_version"]!="1.1.1" or len(natural)!=100 or len(rules)!=100 or len(built)!=100 or len(anomalies)!=50 or
            len(ids)!=250 or set(natural)!=set(rules) or {x["id"] for x in data["index"]["entradas"]}!=ids):
        raise ValueError("EV-ECO active references/cardinality mismatch")
    audit_path=folder/"Everreach_EV_ECO_1_1_Auditoria_Habitats.json"
    habitat=(json.loads(audit_path.read_text(encoding="utf-8-sig")) if audit_path.exists() else
        {"status":"not_available_in_active_package","historical_diagnostic_only":True})
    return {"version":"EV-ECO-1.1.1","hashes":{k:v[1] for k,v in FILES.items()},"natural":natural,
        "rules":rules,"built":built,"anomalies":anomalies,"habitat_audit":habitat,
        "fixtures":r["fixtures_corretivos_v1_1_1"],"active_records":250}


def load_environment_catalog():
    return deepcopy(_load())
