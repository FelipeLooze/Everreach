"""Four-state physical eligibility, distinct from ecological establishment."""
from fractions import Fraction
from math import isfinite
from .catalog import load_environment_catalog
from .config import EnvironmentConfig

LAND_ROLES={"cobertura_principal","cobertura_costeira","modificador_relevo","cobertura_criosferica"}
# Conservative E1 supplements for profiles whose names imply unproven features.
# They do not modify the catalog or make plants necessary for initial potential.
FEATURE_GUARDS={
    "EV-BIO-CAMPO_ALAGAVEL":["hidrologia.inundacao_periodica_confirmada"],
    "EV-BIO-FLORESTA_NEBULOSA":["clima.nevoeiro_orografico_maritimo_confirmado"],
    "EV-BIO-CANION_SECO":["geomorfologia.canion_confirmado"],
    "EV-BIO-TERRAS_ARGILOSAS_ERODIDAS":["geologia.substrato_argiloso_confirmado","geomorfologia.erosao_superficial_confirmada"],
    "EV-BIO-ENCOSTA_INSTAVEL":["geomorfologia.instabilidade_confirmada"],
    "EV-BIO-GRUTA_INUNDADA":["hidrologia.corpo_agua_em_cavidade_confirmado"]}
CONFIRMATION_GUARDS={"EV-BIO-DESERTO_PEDREGOSO":["geologia.afloramento_rochoso_confirmado"],
    "EV-BIO-COLINA_PEDREGOSA":["geologia.afloramento_rochoso_confirmado"],
    "EV-BIO-ESCARPA_ROCHOSA":["geologia.afloramento_rochoso_confirmado"]}
EXTRA_VEGETATED={"EV-BIO-COLINA_ARBORIZADA","EV-BIO-SEMIARIDO_ARBUSTIVO","EV-BIO-TUNDRA_HERBACEA",
    "EV-BIO-TUNDRA_ARBUSTIVA","EV-BIO-TRANSICAO_TAIGA_TUNDRA","EV-BIO-RESTINGA_COSTEIRA","EV-BIO-PRADARIA_COSTEIRA",
    "EV-BIO-VEGETACAO_DUNAS_INTERIORES","EV-BIO-MANGUEZAL","EV-BIO-BREJO_TABOAS","EV-BIO-TURFEIRA"}


def numeric(value):
    if type(value) not in (int,float,Fraction) or (isinstance(value,float) and not isfinite(value)):
        return None
    return value if isinstance(value,Fraction) else Fraction(str(value))


def vegetation_required(rule):
    return rule["confirmacao_ecologica_posterior"].get("obrigatoria_para_confirmar_cobertura_vegetal_estabelecida",False) or rule["ambiente_id"] in EXTRA_VEGETATED


class NaturalClassifier:
    def __init__(self,config=None,catalog=None):
        self.config=config or EnvironmentConfig()
        self.catalog=catalog or load_environment_catalog()
        self.compiled={}
        for identifier,rule in self.catalog["rules"].items():
            specs=[]
            for c in rule["criterios_climaticos_parametrizaveis"]:
                specs.append((c["campo_canonico_proposto"],c["intervalo_referencia"]))
            topo=rule["faixas_topograficas_referencia"]
            for name,field in (("altitude_m","terreno.altitude_m"),("declividade_graus","terreno.declividade_graus")):
                if topo[name] is not None:
                    specs.append((field,topo[name]))
            overrides=self.config.range_overrides.get(identifier,{})
            if set(overrides)-{k for k,_ in specs}:
                raise ValueError("E1 override references an undefined physical range")
            compiled=[]
            for field,bounds in specs:
                bounds=overrides.get(field,bounds)
                if len(bounds)!=2 or any(numeric(v) is None for v in bounds) or numeric(bounds[0])>numeric(bounds[1]):
                    raise ValueError("Invalid E1 physical interval")
                compiled.append((field,tuple(numeric(v) for v in bounds)))
            self.compiled[identifier]=compiled
        if set(self.config.range_overrides)-set(self.compiled):
            raise ValueError("E1 override references an unknown environment")

    def evaluate(self,identifier,facts,*,backend_guards=True):
        rule=self.catalog["rules"][identifier]
        missing=[];conflicts=[];scores=[]
        for field,(low,high) in self.compiled[identifier]:
            value=numeric(facts.get(field))
            if value is None:
                missing.append(field);continue
            if not low<=value<=high:
                conflicts.append(field);continue
            if low==high or field.startswith("terreno."):
                score=1000000
            elif low==0 and field in ("clima.precipitacao_anual_mm","clima.indice_aridez"):
                score=int((high-value)*1000000/(high-low))  # hyperarid is not a poor desert match
            else:
                score=int(4*(value-low)*(high-value)*1000000/(high-low)**2)
            scores.append(score)
        boolean_specs=[(e["campo_canonico_proposto"],e["operador"],e["valor"]) for e in rule["evidencias_fisicas_obrigatorias_all"]]
        if backend_guards:
            if rule["papel_espacial_principal"] in LAND_ROLES:
                boolean_specs.append(("terreno.evidencia_superficie_continental","igual",True))
            boolean_specs.extend((f,"igual",True) for f in FEATURE_GUARDS.get(identifier,[]))
            if self.catalog["natural"][identifier]["grupo"]=="florestas":
                warm=numeric(facts.get("clima.periodo_mais_quente_c"))
                if warm is None:missing.append("clima.periodo_mais_quente_c")
                elif warm<Fraction(self.config.forest_warmest_quarter_min_centi_c,100):conflicts.append("clima.periodo_mais_quente_c")
        for field,operator,target in boolean_specs:
            value=facts.get(field)
            if value is None:
                missing.append(field);continue
            if operator=="igual":
                if type(target) is bool and type(value) is not bool:
                    missing.append(field)
                elif value!=target:
                    conflicts.append(field)
            elif operator=="entre_inclusivo":
                value=numeric(value)
                if value is None:missing.append(field)
                elif not numeric(target[0])<=value<=numeric(target[1]):conflicts.append(field)
            else:
                raise ValueError("Unsupported environmental evidence operator")
        state="incompativel" if conflicts else ("candidato_pendente" if missing else "elegivel")
        score=min(scores) if scores else 1000000
        # Seasonal ranges are explicit preferences, not universal hard constraints.
        for season in rule["criterios_sazonais_referencia"]:
            value=numeric(facts.get(season["campo_canonico_proposto"]))
            if value is not None:
                low,high=map(numeric,season["intervalo_referencia"])
                if not low<=value<=high:
                    score=score//2
        return {"environment_id":identifier,"state":state,"role":rule["papel_espacial_principal"],
            "score_ppm":score if state=="elegivel" else 0,"missing":sorted(set(missing)),"contradictions":sorted(set(conflicts)),
            "confirmation_missing":[k for k in CONFIRMATION_GUARDS.get(identifier,[]) if facts.get(k) is not True],
            "vegetation_establishment_required":vegetation_required(rule),"vegetation_confirmed":False}

    def classify(self,facts):
        results=[self.evaluate(identifier,facts) for identifier in self.compiled]
        eligible=[r for r in results if r["state"]=="elegivel"]
        covers=sorted((r for r in eligible if r["role"] in ("cobertura_principal","cobertura_costeira")),
            key=lambda r:(-r["score_ppm"],r["environment_id"]))
        weighted=[r for r in covers[:self.config.max_secondary+1] if r["score_ppm"]>0]
        if not weighted and covers:
            weighted=covers[:1]  # eligibility at a closed reference boundary is still valid
        total=sum(max(1,r["score_ppm"]) for r in weighted)
        mixture=[{"environment_id":r["environment_id"],"weight_ppm":max(1,r["score_ppm"])*1000000//total} for r in weighted] if total else []
        if mixture:
            mixture[0]["weight_ppm"]+=1000000-sum(r["weight_ppm"] for r in mixture)
        ecotone=len(weighted)>1 and weighted[1]["score_ppm"]*1000000>=weighted[0]["score_ppm"]*self.config.ecotone_relative_score_ppm
        return {"results":results,"primary_potential":mixture[0]["environment_id"] if mixture else None,
            "secondary_potential":[r["environment_id"] for r in mixture[1:]],"mixture":mixture,"ecotone":ecotone,
            "feature_layers":[r["environment_id"] for r in eligible if r["role"] not in ("cobertura_principal","cobertura_costeira")],
            "vegetation_confirmed":False,"spawn_authorized":False}


def evaluate_built(rule,facts,*,persistence_verified=False):
    c=rule["correspondencia_tipificada_obrigatoria"]
    value=facts.get(c["campo_tipo_funcional"])
    if value is not None and value!=rule["ambiente_id"]:
        return "incompativel"
    required=[c["campo_id_instancia"],c["campo_tipo_funcional"],c["campo_ancora_espacial"]]
    if not persistence_verified or any(not isinstance(facts.get(k),str) or not facts[k].strip() for k in required) or not facts.get("estrutura.estado"):
        return "candidato_pendente"
    state=facts["estrutura.estado"]
    if state not in {"registrada","ativa","concluida","arruinada","abandonada","colapsada","antiga"}:
        return "candidato_pendente"
    if c["estado_minimo"]=="arruinada" and state not in {"arruinada","abandonada","colapsada","antiga"}:
        return "incompativel"
    if c["estado_minimo"]=="ativa" and state!="ativa":
        return "candidato_pendente"
    return "elegivel"


def evaluate_anomaly(rule,facts,*,persistence_verified=False):
    c=rule["vinculo_canonico_especifico_obrigatorio"]
    keys=[c[k] for k in ("campo_autorizacao_id","campo_autorizacao_anomalia","campo_fonte_id","campo_fonte_anomalia","campo_ancora_fonte","campo_ancora_registro")]
    if not persistence_verified or any(not isinstance(facts.get(k),str) or not facts[k].strip() or
            facts[k].strip().casefold() in {"*","all","any","generica","generic"} or "*" in facts[k] or "?" in facts[k] for k in keys):
        return "candidato_pendente"
    if (facts[c["campo_autorizacao_anomalia"]]!=rule["ambiente_id"] or facts[c["campo_fonte_anomalia"]]!=rule["ambiente_id"] or
            facts[c["campo_ancora_fonte"]]!=facts[c["campo_ancora_registro"]]):
        return "candidato_pendente"
    return "elegivel"
