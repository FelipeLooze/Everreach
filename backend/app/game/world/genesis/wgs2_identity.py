"""WGS2.4 instance facts derived from v24 and confirmed local authorities.

These are narrator inputs, not new environmental or resource authorities.
"""

VERSION = "WGS2_IDENTITY_R1"

CLUES = {
    "EV-LOC-0020": "Um terraco aberto se eleva acima do entorno ao {direction}.",
    "EV-LOC-0021": "Uma area de savana aberta se distingue ao {direction}.",
    "EV-LOC-0023": "Faixas escuras interrompem a campina ao {direction}.",
    "EV-LOC-0033": "Lajes em degraus marcam uma passagem rochosa ao {direction}.",
    "EV-LOC-0037": "Paredes lisas estreitam uma garganta ao {direction}.",
    "EV-LOC-0041": "Taludes sobrepostos recortam o relevo ao {direction}.",
    "EV-LOC-0049": "Uma abertura com colunas rochosas aparece ao {direction}.",
    "EV-LOC-0051": "Uma abertura inclinada na rocha aparece ao {direction}.",
    "EV-LOC-0081": "Cordoes de dunas marcam o horizonte ao {direction}.",
    "EV-LOC-0082": "Um arco rochoso sombreia o solo ao {direction}.",
    "EV-LOC-0084": "Uma extensao de argila rachada aparece ao {direction}.",
    "EV-LOC-0086": "Uma planicie de seixos claros se estende ao {direction}.",
    "EV-LOC-0193": "Paredoes delimitam um vale estreito ao {direction}.",
    "EV-LOC-0225": "Uma faixa de transicao entre campo e bosque surge ao {direction}.",
    "EV-LOC-0226": "Uma cornija rochosa marca a encosta ao {direction}.",
}

FOCUS = {
    "area_aberta": "extensao_e_cobertura_potencial",
    "relevo_rochoso": "declividade_e_passagem",
    "interior_natural": "entrada_e_saida_confirmadas",
    "paisagem_arida": "superficie_e_habitat_potencial",
    "ecotono": "transicao_ambiental_potencial",
    "manifestacao_local": "geometria_observavel_sem_anomalia_ativa",
}

# E1 habitat is potential and cannot establish individual plants, weather or
# thermal protection. Keep the v24 shape while omitting unverified claims.
SAFE_VISUAL = {
    "EV-LOC-0020": "Um terraço aberto e relativamente plano domina vales menores.",
    "EV-LOC-0021": "Uma área aberta associada ao habitat de savana ocupa a paisagem.",
    "EV-LOC-0023": "Faixas de solo escuro cruzam terreno aberto.",
    "EV-LOC-0037": "Paredes polidas comprimem um corredor rochoso.",
    "EV-LOC-0081": "Cordões de areia recortam o horizonte.",
    "EV-LOC-0082": "Um arco rochoso sombreia parte do chão.",
    "EV-LOC-0225": "Uma faixa marca a transição entre habitats potenciais de bosque e campo.",
    "EV-LOC-0226": "Um ressalto rochoso marca a encosta exposta.",
    "EV-LOC-0236": "Uma depressão sombreada se destaca na encosta árida.",
}
UNCONFIRMED_VARIATIONS = {"altura_vegetacao", "cobertura_arvores", "exposicao_vento",
                          "sazonalidade", "duracao", "vias_acesso", "saloes",
                          "acessibilidade", "visibilidade"}


def presentation(archetype_id, record, variations):
    visual = SAFE_VISUAL.get(archetype_id, record["descricao_visual"])
    visible = {key: value for key, value in variations.items()
               if key not in UNCONFIRMED_VARIATIONS}
    return visual, visible


def facts(archetype_id, record, dimensions, variations, decision, *, interior=False):
    """No inferred minerals, species, water, wind shelter or hidden routes."""
    geometry = record["geometria"]
    visual, visible_variations = presentation(archetype_id, record, variations)
    confirmed = decision.get("context", {})
    physical = {
        "T1_height_mm": confirmed.get("height_mm"),
        "T1_slope_ppm": confirmed.get("slope_ppm"),
        "reference_ocean_H1": confirmed.get("reference_ocean_H1"),
        "J1_substrates": confirmed.get("substrates"),
        "E1_signature": confirmed.get("E1_signature") or confirmed.get("authority_signature"),
        "E1_eligible_habitat_ids": confirmed.get("E1_eligible_habitat_ids"),
    }
    return {
        "version": VERSION,
        "archetype_id": archetype_id,
        "observable_visual": visual,
        "geometry_type": geometry.get("tipo_espacial"),
        "investigation_focus": FOCUS.get(geometry.get("tipo_espacial"), "geometria_local"),
        "horizontal_span_m": dimensions["horizontal_span_m"],
        "orientation_degrees": dimensions.get("orientation_degrees"),
        "catalog_variations": visible_variations,
        "confirmed_physical": {key: value for key, value in physical.items() if value is not None},
        "interior_authorized": interior and bool(geometry.get("interior_potencial")),
        "catalog_subareas_possible": bool(geometry.get("subareas_potenciais")),
        "surface_materials_unconfirmed": True,
        "resources_unconfirmed": True,
    }
