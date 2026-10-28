#!/usr/bin/env python3
"""Contract tests for EV-ECO-1.1.1. Python stdlib only. Never mutates World Genesis."""
import json, pathlib, collections, hashlib
HERE=pathlib.Path(__file__).resolve().parent
D=json.load(open(HERE/'Everreach_EV_ECO_1_1_1_Regras_Fisicas_250.json',encoding='utf-8'))

def natural(item, data):
    incompatible=False; pending=False
    for e in item['criterios_climaticos_parametrizaveis']:
        k=e['campo_canonico_proposto']
        if k not in data or data[k] is None:pending=True;continue
        val=data[k]
        if not isinstance(val,(int,float)) or isinstance(val,bool):pending=True;continue
        lo,hi=e['intervalo_referencia']
        if not lo<=val<=hi:incompatible=True
    for e in item['evidencias_fisicas_obrigatorias_all']:
        k=e['campo_canonico_proposto']
        if k not in data or data[k] is None:pending=True;continue
        op=e['operador']
        if op=='igual' and data[k]!=e['valor']:incompatible=True
        elif op=='entre_inclusivo':
            value=data[k];lo,hi=e['valor']
            if not isinstance(value,(int,float)) or isinstance(value,bool):pending=True
            elif not lo<=value<=hi:incompatible=True
    return 'incompativel' if incompatible else ('candidato_pendente' if pending else 'elegivel')

def built(item,data):
    # Missing record != incompatible. A known wrong type is incompatible.
    c=item['correspondencia_tipificada_obrigatoria']
    typ=data.get(c['campo_tipo_funcional'])
    if typ is not None and typ!=c['valor_tipo_funcional']:return 'incompativel'
    if any(not data.get(k) for k in (c['campo_id_instancia'],c['campo_tipo_funcional'],c['campo_ancora_espacial'])):
        return 'candidato_pendente'
    # For this contract test, state=registered or active. The backend must check actual persistence.
    state=data.get('estrutura.estado')
    if not state:return 'candidato_pendente'
    if c['estado_minimo']=='arruinada' and state not in {'arruinada','abandonada','colapsada','antiga'}:return 'incompativel'
    if c['estado_minimo']=='ativa' and state!='ativa':return 'candidato_pendente'
    return 'elegivel'

def anomaly(item,data):
    c=item['vinculo_canonico_especifico_obrigatorio']
    keys=[c['campo_autorizacao_id'],c['campo_autorizacao_anomalia'],c['campo_fonte_id'],c['campo_fonte_anomalia'],c['campo_ancora_fonte'],c['campo_ancora_registro']]
    if any(not data.get(k) for k in keys):return 'candidato_pendente_bloqueado'
    if any(data[k] in {'*','all','any','generica','ANY'} for k in keys):return 'candidato_pendente_bloqueado'
    if data[c['campo_autorizacao_anomalia']] != item['ambiente_id']:return 'candidato_pendente_bloqueado'
    if data[c['campo_fonte_anomalia']] != item['ambiente_id']:return 'candidato_pendente_bloqueado'
    if data[c['campo_ancora_fonte']] != data[c['campo_ancora_registro']]:return 'candidato_pendente_bloqueado'
    return 'elegivel_autorizado_ainda_nao_instanciado'

def run():
    tests={}
    def check(name,condition):
        tests[name]=bool(condition)
        if not condition:raise AssertionError(name)
    nn=D['ambientes_naturais']; bb=D['camadas_construidas']; aa=D['camadas_anomalas']
    check('100 naturais',len(nn)==100)
    check('100 construidos',len(bb)==100)
    check('50 anomalos',len(aa)==50)
    ids=[x['ambiente_id'] for arr in [nn,bb,aa] for x in arr]
    check('250 IDs unicos',len(ids)==250 and len(set(ids))==250)
    check('nenhuma vegetacao na elegibilidade fisica',not any(e['campo_canonico_proposto'].startswith('vegetacao.') for x in nn for e in x['evidencias_fisicas_obrigatorias_all']))
    check('nenhuma dependencia de vegetacao no P1',not any(e.get('fonte_world_genesis_sugerida')=='P1' and e['campo_canonico_proposto'].startswith('vegetacao.') for x in nn for e in x['evidencias_fisicas_obrigatorias_all']))
    check('toda vegetacao separada por fase',all('confirmacao_ecologica_posterior' in x for x in nn))
    check('nao permite spawn fisico',all(x['spawns_automaticos_autorizados'] is False for x in nn+bb))
    check('100 ambientes construidos tipados',all(x['correspondencia_tipificada_obrigatoria']['valor_tipo_funcional']==x['ambiente_id'] for x in bb))
    check('100 construidos exigem id localizacao',all(x['correspondencia_tipificada_obrigatoria']['exige_tipo_e_id_e_ancora_validos'] for x in bb))
    check('50 autorizacoes especificas',all(x['vinculo_canonico_especifico_obrigatorio']['anomalia_id_requerida']==x['ambiente_id'] for x in aa))
    check('50 anomalias inativas',all(not x['ativo_por_padrao'] for x in aa))
    check('50 anomalias sem spawn',all(x['nao_spawn_automatico'] for x in aa))
    check('25+ familias 6a linkadas sem autorizar',sum(bool(x['correspondencia_tipificada_obrigatoria']['referencias_6a_de_suporte_nao_suficientes_isoladamente']) for x in bb)>=25)
    nmap={x['ambiente_id']:x for x in nn}; bmap={x['ambiente_id']:x for x in bb}; amap={x['ambiente_id']:x for x in aa}
    count=0
    for fix in D['fixtures_corretivos_v1_1_1']:
        x=fix['ambiente_id']; cat=fix['categoria']; data=fix['dados']
        result={'natural':lambda:natural(nmap[x],data),'construido':lambda:built(bmap[x],data),'anomalo':lambda:anomaly(amap[x],data)}[cat]()
        check('fixture '+fix['caso'],result==fix['esperado_avaliacao']);count+=1
    check('15 fixtures corretivas',count==15)
    # Generic structures, a single authorization must never satisfy arbitrary other IDs.
    d={'estrutura.id_persistente':'BLD-1','estrutura.tipo_funcional_ambiente_id':'EV-AMB-FORJA_ATIVA','estrutura.localizacao_mapeada_id':'LOC-1','estrutura.estado':'ativa'}
    check('forja nao classifica escola',built(bmap['EV-AMB-ESCOLA_COMUNITARIA'],d)=='incompativel')
    check('forja nao classifica biblioteca',built(bmap['EV-AMB-BIBLIOTECA_CIVICA'],d)=='incompativel')
    check('forja nao classifica armazem',built(bmap['EV-AMB-CELEIRO_ARMAZEM'],d)=='incompativel')
    check('ausencia de clima continua pendente',natural(nmap['EV-BIO-FLORESTA_TROPICAL_UMIDA'],{})=='candidato_pendente')
    check('falsa passagem hidrica impede confirmacao',natural(nmap['EV-BIO-MANGUEZAL'],{'clima.temperatura_media_anual_c':25,'clima.precipitacao_anual_mm':1900,'hidrologia.solo_saturado_confirmado':False})=='incompativel')
    print('EV-ECO-1.1.1:',len(tests),'testes aprovados; 15 cenarios; nenhum teste do backend executado.')
    return {'status':'aprovada_validacao_estrutural_e_de_contrato','testes':tests,'testes_aprovados':len(tests),'cenarios':count}
if __name__=='__main__':run()
