"""Phase 0.9.2: fixed-geography C2/C3 water balances and real disposable W2/P1 proof."""
from collections import defaultdict
import json
from pathlib import Path
import time
import tracemalloc
from tempfile import TemporaryDirectory
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db import models
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.world_water import GenesisWaterPlan
from app.db.models.world_hydrology_regional import GenesisHydrologyRegion
from app.game.world.genesis.climate.plan import load_climate_plan
from app.game.world.genesis.environment.adapter import EnvironmentSampler
from app.game.world.genesis.environment.config import EnvironmentConfigC3
from app.game.world.genesis.hydrology.regional import build_regional_hydrology
from app.game.world.genesis.hydrology.regional_service import initialize_regional_hydrology
from app.game.world.genesis.water.config import WaterConfigC3R155
from app.game.world.genesis.water.plan import build_water_plan,load_water_plan,checksum
from app.game.world.genesis.water.preview import metrics,write_preview
from app.game.world.genesis.water.balance import STORES
from app.game.world.genesis.hydro_geometry.service import initialize_geometry
from app.game.world.genesis.water_reconciliation.service import (initialize_reconciliation,prepare_water_domain,get_water_domain,reconcile,get_revision)
from app.game.world.genesis.water_reconciliation.practical.config import PracticalConfig
from app.game.world.genesis.water_reconciliation.practical.service import initialize_practical_hydrology,prepare_natural_passage,get_local_account,POOL
from app.game.world.genesis.water_reconciliation.practical.proof import inspect_parcel,select_candidates
from app.game.world.genesis.terrain.address import TerrainTile
from scripts.validate_environment import environment_inputs,import_sources
from app.game.world.genesis.water_reconciliation.config import RevisionRequest,TransferIntent

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'artifacts/water-c3-compatibility'


def inputs(seed):
    original=environment_inputs(seed,63710000)
    data=json.loads((ROOT/f'artifacts/climate-c3-final/seed-{seed}/R1-55-plan.json').read_text())
    climate=load_climate_plan(data,original.climate.source_signature,original.h1.signature,63710000,original.climate.sea_level_m)
    return original,EnvironmentSampler(original.regional,original.h1,climate,EnvironmentConfigC3())


def fixed_evidence(original,seed):
    path=ROOT/f'artifacts/water-w1/seed-{seed}-r63710000/hr1-evidence.json'
    if path.exists():return json.loads(path.read_text()),'existing fixed C2 manifest, reused identically for both climates'
    h1=original.h1;nodes=set()
    # Geographic ordering only. No runoff, climate or gameplay level is consulted.
    edges=sorted((i for i in h1.channel_index if h1.drainage.parent[i]>=0),
        key=lambda i:(-(h1.drainage.head[i]-h1.drainage.head[h1.drainage.parent[i]]),i))
    for i in edges:
        pair={i,h1.drainage.parent[i]}
        if len(nodes|pair)<=32:nodes|=pair
        if len(nodes)==32:break
    return [build_regional_hydrology(original.regional.terrain.plan.source,h1,i) for i in sorted(nodes)],'up to 32 geographic H1 nodes, ordered by head drop; same evidence in both climates'


def region_metrics(water,reference_C2=None):
    h1=water.hydrology;groups=defaultdict(lambda:defaultdict(int))
    for i,area in enumerate(h1.cell_area_m2):
        if h1.drainage.marine[i] or h1.heights[i]<h1.sea_level_m:continue
        total_p=sum(s[i] for s in water.precipitation_mm);total_pet=sum(s[i] for s in water.pet_mm)
        def category(p,pet):return 'energy_limited' if not pet else 'humid' if p>=pet else 'moderate' if 2*p>=pet else 'semiarid' if 5*p>=pet else 'arid'
        keys=['land','climate/'+category(total_p,total_pet)]
        if reference_C2 is not None:
            p=sum(s[i] for s in reference_C2.precipitation_mm);e=sum(s[i] for s in reference_C2.pet_mm)
            keys.append('same_C2_region/'+category(p,e))
        for key in keys:
            row=groups[key];row['area_m2']+=area;row['nodes']+=1
            for name in ('precipitation','pet','evapotranspiration','local_runoff','outflow','ocean_export'):
                row[name+'_liters']+=sum(s['fluxes'][name][i] for s in water.solution.periods)
            row['opening_stock_liters']+=sum(v[i] for v in water.solution.initial_stores)
            for name in STORES:row['final_'+name+'_liters']+=water.solution.periods[-1]['stores'][name][i]
            runoff=sum(s['fluxes']['local_runoff'][i] for s in water.solution.periods)
            if not runoff:row['area_without_local_runoff_m2']+=area
            if water.config.source_climate_version==3:
                for s,period in enumerate(water.solution.periods):
                    r=water.atmospheric_recycling_mm[s][i]*area
                    row['atmospheric_recycling_potential_liters']+=r
                    row['atmospheric_net_deposition_diagnostic_liters']+=water.atmospheric_net_deposition_mm[s][i]*area
                    row['ET_support_shortfall_to_atmospheric_hypothesis_liters']+=max(0,r-period['fluxes']['evapotranspiration'][i])
    return {key:{**row,'mean_depth_mm':{k[:-7]:v/row['area_m2'] for k,v in row.items() if k.endswith('_liters')},
        'zero_local_runoff_area_fraction':row['area_without_local_runoff_m2']/row['area_m2']} for key,row in groups.items()}


def import_disposable(db,sampler,water,regions):
    cid=import_sources(db,sampler,sampler.regional.terrain.plan.source.seed);initialize_regional_hydrology(db,cid);initialize_geometry(db,cid)
    for region in regions:
        db.add(GenesisHydrologyRegion(campaign_id=cid,node=region['node'],signature=region['signature'],baseline=region,
            baseline_checksum=checksum(region),changes={}))
    db.flush()
    from app.db.models.world_hydrology import GenesisHydrologyPlan
    from app.db.models.world_climate import GenesisClimatePlan
    h=db.get(GenesisHydrologyPlan,cid);c=db.get(GenesisClimatePlan,cid);payload=water.to_dict()
    row=GenesisWaterPlan(campaign_id=cid,water_version=1,signature=water.signature,config=water.config.model_dump(),
        hydrology_signature=h.signature,hydrology_checksum=h.payload_checksum,climate_signature=c.signature,climate_checksum=c.payload_checksum,
        hr_signature=water.hr_signature,manifest=list(water.manifest),payload_checksum=checksum(payload),plan=payload)
    db.add(row);db.flush();return cid,row


def requests(db,cid,proof,evidence):
    node=evidence.node;q=proof['allocation']['vertex_quota_liters'];amount=q[proof['source_vertex']]+q[proof['target_vertex']]
    allocation=RevisionRequest(operation_id='C3-allocate',logical_minute=0,expected_heads={str(node):get_water_domain(db,cid,node)['head_id']},
        transfers=[TransferIntent(transfer_id='C3-allocate',source_node=node,target_node=node,source_account='w1:surface',target_account=POOL,
            amount_liters=amount,evidence_keys=[evidence.evidence_key])])
    return allocation


def persistent_demo(sampler,water,regions,output):
    old=json.loads((ROOT/'artifacts/practical-hydrology-p1/probe.json').read_text())['found'];config=PracticalConfig.model_validate(old['config'])
    # Reinspect geometry/quota under the new water authority; do not alter an old proof's signature.
    proof,trial=inspect_parcel(water,sampler.regional.terrain,TerrainTile(*old['allocation']['tile']),config)
    trials=[{'origin':'same historical geographic parcel, freshly measured',**trial}]
    if proof is None:proof,extra=select_candidates(water,sampler.regional.terrain,config);trials+=extra
    if proof is None:raise RuntimeError('No C3 P1 proof in bounded search; no volumes will be fabricated')
    (output/'natural-proof.json').write_text(json.dumps({'proof':proof,'trials':trials},indent=2),encoding='utf-8')
    with TemporaryDirectory(prefix='everreach-water-c3-') as temp:
        engine=create_engine('sqlite:///'+(Path(temp)/'proof.db').as_posix());event.listen(engine,'connect',enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
        with Session(engine) as db:
            cid,row=import_disposable(db,sampler,water,regions);initialize_reconciliation(db,cid,cutover_minute=0)
            initialize_practical_hydrology(db,cid,config);evidence=prepare_natural_passage(db,cid,proof);prepare_water_domain(db,cid,evidence.node)
            before=get_water_domain(db,cid,evidence.node);original_hash=row.payload_checksum
            allocated=reconcile(db,cid,requests(db,cid,proof,evidence))
            request=RevisionRequest(operation_id='C3-natural-flow',logical_minute=config.episode_minutes,
                expected_heads={str(evidence.node):get_water_domain(db,cid,evidence.node)['head_id']},
                transfers=[TransferIntent(transfer_id='C3-natural-flow',source_node=evidence.node,target_node=evidence.node,
                    source_account=evidence.baseline['source_account'],target_account=evidence.baseline['target_account'],
                    amount_liters=proof['suggested_transfer_liters'],evidence_keys=[evidence.evidence_key])])
            started=time.perf_counter();moved=reconcile(db,cid,request);elapsed=time.perf_counter()-started
            assert reconcile(db,cid,request).revision_id==moved.revision_id
            after=get_water_domain(db,cid,evidence.node)
            assert sum(before['state']['accounts'].values())==sum(after['state']['accounts'].values())
            assert checksum(row.plan)==original_hash
            target=evidence.baseline['target_account'];target_liters=get_local_account(db,cid,target)['liters'];rid=moved.revision_id
            data={'proof':proof,'allocated':allocated.payload,'flow':moved.payload,'before':before,'after':after,
                'node':evidence.node,'climate_signature':water.climate_signature,'forcing_contract':water.config.forcing_contract,
                'target_liters':target_liters,'reconcile_seconds':elapsed,'perennial':None,'real_save_modified':False}
            db.commit()
        with Session(engine) as db:
            assert get_revision(db,cid,rid)['payload']==data['flow']
            assert get_local_account(db,cid,target)['liters']==target_liters
            assert reconcile(db,cid,request).revision_id==rid
            data['committed_and_reopened']=True
        engine.dispose()
    (output/'persistent-proof.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    return {k:data[k] for k in ('node','forcing_contract','reconcile_seconds','committed_and_reopened','target_liters')}


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True);cases=[]
    for seed in (42,0,7,2026,12345):
        folder=OUTPUT/f'seed-{seed}';folder.mkdir(exist_ok=True);original,new=inputs(seed)
        before=checksum(original.climate.to_dict()),checksum(new.climate.to_dict()),checksum(original.regional.terrain.plan.source.to_dict())
        regions,policy=fixed_evidence(original,seed);plans={};records={}
        for name,sampler,config in (('C2',original,None),('C3',new,WaterConfigC3R155())):
            started=time.perf_counter();plan=build_water_plan(sampler.regional.terrain.plan.source,sampler.h1,sampler.climate,regions,config=config);elapsed=time.perf_counter()-started
            payload=json.dumps(plan.to_dict(),separators=(',',':'));started=time.perf_counter()
            assert load_water_plan(json.loads(payload),sampler.h1,sampler.climate,plan.hr_signature)==plan
            loading=time.perf_counter()-started
            plans[name]=plan;records[name]={'metrics':metrics(plan),'build_seconds':elapsed,'load_seconds':loading,'payload_bytes':len(payload.encode())}
            (folder/(name+'-water-plan.json')).write_text(payload,encoding='utf-8')
            (folder/(name+'-hr1-evidence.json')).write_text(json.dumps(regions,separators=(',',':')),encoding='utf-8')
            write_preview(plan,folder/name,seed)
            if name=='C2':
                oldpath=ROOT/f'artifacts/water-w1/seed-{seed}-r63710000/plan.json'
                if oldpath.exists():assert json.loads(oldpath.read_text())==json.loads(payload)
        for name,plan in plans.items():records[name]['regions']=region_metrics(plan,plans['C2'])
        assert plans['C2'].manifest==plans['C3'].manifest and plans['C2'].support==plans['C3'].support
        result={'seed':seed,'radius_m':63710000,'evidence_policy':policy,'same_evidence_and_geography':True,'balances':records,
            'sources_unchanged':before==(checksum(original.climate.to_dict()),checksum(new.climate.to_dict()),checksum(original.regional.terrain.plan.source.to_dict()))}
        if seed==42:
            tracemalloc.start();measured=build_water_plan(new.regional.terrain.plan.source,new.h1,new.climate,regions,config=WaterConfigC3R155());retained,peak=tracemalloc.get_traced_memory();tracemalloc.stop();assert measured==plans['C3']
            result['memory']={'peak_bytes':peak,'retained_bytes':retained,'scope':'W1 build including C3 projection, physical authorities preloaded, not RSS'}
            result['persistence']=persistent_demo(new,plans['C3'],regions,folder)
        (folder/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8');cases.append(result)
        print(json.dumps({'seed':seed,'C2_runoff_mm':records['C2']['metrics']['land_mean_local_runoff_mm'],'C3_runoff_mm':records['C3']['metrics']['land_mean_local_runoff_mm'],
            'C3_residual_liters':records['C3']['metrics']['year_residual_liters']}),flush=True)
    (OUTPUT/'suite.json').write_text(json.dumps({'cases':cases,'real_saves_modified':False,'automatic_activation':False,'climate_recalibrated':False},indent=2),encoding='utf-8')


if __name__=='__main__':main()
