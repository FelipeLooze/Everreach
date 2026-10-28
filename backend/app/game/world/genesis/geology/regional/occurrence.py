"""D14 opportunities and length-calibrated experimental sources; no global cap."""
from ..adapter import evaluate_opportunities
from ..catalog import load_catalog
from .field import adapt_formation
from .config import RegionalPolicy
from ...terrain.field import checksum

INTENSITY_PER_KM_PPM = {"comum":35000,"incomum":8000,"raro":1000,"muito_raro":50,"lendario":0}


def opportunities(formation,signature,catalog=None):
    catalog = catalog or load_catalog()
    assessment = evaluate_opportunities(adapt_formation(formation,signature),catalog)
    eligible,blocked = [],[]
    for opportunity in assessment["opportunities"]:
        material = catalog["materials"][opportunity["material_id"]]
        geometry = material["ocorrencia_geologica_v4"]["geometria_e_disponibilidade"]
        low,high = geometry["indice_profundidade_referencia_intervalo_0_100"]
        if not low<=formation["depth_index_0_100"]<=high:
            blocked.append({"material_id":material["id"],"reason":"conservative_D14_reference_depth_filter"})
        elif formation["contact_fragment_pending"]:
            blocked.append({"material_id":material["id"],"reason":"anchor_outside_J1_contact_fragment"})
        else:
            eligible.append(opportunity)
    return {"opportunities":eligible,"blocked_materials":blocked,"bridges":assessment["bridges"]}


def select_sources(formation,signature,policy=None,catalog=None):
    policy = policy or RegionalPolicy()
    catalog = catalog or load_catalog()
    selected = []
    for opportunity in opportunities(formation,signature,catalog)["opportunities"]:
        material = catalog["materials"][opportunity["material_id"]]
        if (opportunity["rarity"]=="lendario" or material["origem_condicional"]["exige_autorizacao_canonica_para_fonte_anomala"] or
                material["ocorrencia_geologica_v4"]["formacao_de_fonte"]["requer_condicao_canonica_excepcional"]):
            continue
        # p = lambda*L/(1+lambda*L), a frozen bounded RPG occurrence model.
        numerator = INTENSITY_PER_KM_PPM[opportunity["rarity"]]*policy.rate_factor_ppm*formation["structure_length_m"]
        denominator = 10**15+numerator
        ticket = int(checksum([signature,"JR1_source",opportunity["opportunity_id"]])[:16],16)
        if ticket*denominator>=numerator*2**64:
            continue
        low,high = material["ocorrencia_geologica_v4"]["geometria_e_disponibilidade"]["volume_deposito_referencia_intervalo_unidades_abstratas"]
        volume = low+int(checksum([signature,opportunity["opportunity_id"],"volume"])[:16],16)%(high-low+1)
        selected.append({**opportunity,"kind":"regional_deposit_jr1","regional_version":1,
            "formation_id":formation["formation_id"],"parent_unit_id":formation["parent_unit_id"],
            "deposit_id":"deposit-jr1:"+checksum([signature,policy.model_dump(),opportunity["opportunity_id"]])[:32],
            "initial_volume_units":volume,"volume_unit":"D14_abstract_not_kg_or_liters",
            "anchor_surface_point":formation["anchor_point"],"depth_index_0_100":formation["depth_index_0_100"],
            "occurrence_policy":policy.model_dump(),"eligible_length_m":formation["structure_length_m"],
            "selection_threshold_ppm":numerator*1000000//denominator,
            "exposure_model":formation["exposure"],"access_authorized":False,"experimental_only":True,
            "eligible_not_instantiated":True,"historical_v4_intensity_used":False})
    return selected
