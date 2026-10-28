"""Real Uvicorn/HTTP TP1 playtest. Always creates its own temporary database.

Run from backend: .venv/Scripts/python.exe scripts/playtest_genesis_territory.py
No browser claims: AI roles use the supported disabled provider so this measures
mechanics/fallback narration without network cost. The server is really restarted.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def run():
    backend = Path(__file__).resolve().parents[1]
    normal = backend/'everreach.db'
    original = hashlib.sha256(normal.read_bytes()).hexdigest() if normal.exists() else None
    folder = Path(tempfile.mkdtemp(prefix='everreach-tp1-'))
    database = folder/'playtest.sqlite'
    assert database.resolve() != normal.resolve() and not database.exists()
    env = {**os.environ, 'DATABASE_URL':'sqlite:///'+database.as_posix(), 'PYTHONIOENCODING':'utf-8'}
    for role in ('INTENT','NARRATIVE','REGENERATION'):
        env[role+'_LLM_PROVIDER']='disabled'
        env[role+'_LLM_FALLBACK_PROVIDER']=''
        env[role+'_LLM_FALLBACK_MODEL']=''
    os.environ.update(env)
    sys.path.insert(0,str(backend))
    with (folder/'migration.log').open('w',encoding='utf-8') as log:
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'], cwd=backend,env=env,
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    def request(path, data=None):
        req=Request(base+path, data=json.dumps(data).encode() if data is not None else None,
                    headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=180) as response:return json.load(response)
        except HTTPError as exc:
            raise AssertionError(f'{path}: {exc.code} {exc.read().decode()}') from exc
    server_log=(folder/'server.log').open('a',encoding='utf-8')
    def launch():
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],
            cwd=backend,env=env,stdout=server_log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('Server exited; see '+str(folder))
            try:request('/openapi.json');return process
            except OSError:time.sleep(.2)
        process.terminate();process.wait();raise RuntimeError('Server startup timeout')
    def rows(sql,params=()):
        with sqlite3.connect(database) as db:
            db.row_factory=sqlite3.Row
            return [dict(r) for r in db.execute(sql,params)]
    report={'database':str(database),'llm':'disabled: no external inference cost measured','browser':'unavailable', 'seeds':[]}
    process=launch()
    try:
        for seed in (42,8675309):
            result={'seed':seed,'timings_seconds':{},'journey':[]}
            campaign=request('/api/campaigns',{'name':f'TP1 HTTP {seed}','world_profile':'world_genesis_ap1_v1','world_seed':seed})
            cid=campaign['id']; actor=request(f'/api/campaigns/{cid}/characters',{'name':'Exploradora'})
            aid=actor['id'];result['campaign_id']=cid;result['character_id']=aid
            prefix=f'/api/campaigns/{cid}';query=f'?character_id={aid}'
            def timed(label,path,body=None):
                t=time.perf_counter();value=request(prefix+path+query,body)
                result['timings_seconds'][label]=time.perf_counter()-t
                return value
            turn=0
            def action(label,text,plant=None):
                nonlocal turn
                turn+=1;body={'text':text,'action_key':f'tp1-live-{turn}'}
                if plant:body['plant_action']=plant
                return timed(label,'/actions',body)
            start=timed('start_cold' if seed==42 else 'start_second_seed','/start',{})
            root=start['state']['location']['id'];current=root;visited=[root]
            def describe(lid):
                row=rows('select genesis_site from locations where id=?',(lid,))[0]
                site=json.loads(row['genesis_site'])
                community=json.loads(rows('select baseline from genesis_vegetation_communities where campaign_id=? and community_id=?',(cid,site['community_id']))[0]['baseline'])
                # Separate read-only E1 diagnostic (not a new player endpoint).
                from sqlalchemy import create_engine
                from sqlalchemy.orm import Session
                from app.db import models  # populate metadata
                from app.game.world.genesis.environment.service import query_environment
                from app.game.world.genesis.sphere_topology import SurfacePoint
                engine=create_engine('sqlite:///file:'+database.as_posix()+'?mode=ro&uri=true')
                with Session(engine) as db:
                    t=time.perf_counter();environment=query_environment(db,cid,SurfacePoint(*site['point']))
                    cold=time.perf_counter()-t
                    t=time.perf_counter();query_environment(db,cid,SurfacePoint(*site['point']))
                    warm=time.perf_counter()-t
                engine.dispose()
                return {'location_id':lid,'site':site,'environment_potential':community['E1_primary_potential'],
                        'cover_ppm':community['cover_ppm'],'physical_inputs':environment['baseline']['physical_inputs'],
                        'environment_read_seconds':cold,'environment_read_warm_seconds':warm}
            result['journey'].append(describe(root))
            look=action('plants_root','Observo a vegetação.',{'kind':'look'})
            plants=look['plant_result']['individuals'];assert plants
            # Select an actually authorized plant protocol; no catalog editing.
            sys.path.insert(0,str(backend))
            os.environ.update(env)
            from app.game.world.genesis.vegetation.catalog import load_flora_catalog
            catalog=load_flora_catalog()
            from app.game.world.genesis.playable import FIELD_CAPABILITIES
            eligible=[]
            for p in plants:
                baseline=json.loads(rows('select baseline from genesis_plant_individuals where campaign_id=? and individual_id=?',(cid,p['individual_id']))[0]['baseline'])
                for part in p['parts']:
                    canonical=next(k for k in catalog.species[baseline['species_id']].parts() if k['id']==part['part_id'])
                    proto=canonical['protocolo_campo_v7']
                    if part['available_now'] and proto['dificuldade_base_0_100']<=35 and set(proto['capacidades_necessarias_da_ferramenta'])<=FIELD_CAPABILITIES and any(k.endswith('principal_id') and v=='EV-PROF-BOT-002' for k,v in proto.items()):eligible.append((p,part))
            assert eligible
            target,part=eligible[0]
            action('inspect_root','Examino a planta.',{'kind':'observe','individual_id':target['individual_id']})
            tool=next(i['item_instance_id'] for i in start['state']['inventory']['items'] if i['name']=='Tesoura de campo')
            harvest=action('harvest','Coleto uma parte.',{'kind':'harvest','individual_id':target['individual_id'],
                'part_id':part['part_id'],'quantity':1,'tool_instance_id':tool})
            receipt=harvest['plant_result'];assert receipt['quantity']==1 and receipt['exported_mass_mg']>0
            assert any(i['item_instance_id']==receipt['item_instance_id'] for i in harvest['state']['inventory']['items'])
            result['harvest']=receipt
            for index in range(2):
                action(f'observe_{index}','Olho ao redor.')
                edges=rows('select c.* from location_connections c join character_connection_discoveries d on d.connection_id=c.id where c.from_location_id=? and c.active=1 and d.character_id=? order by c.direction',(current,aid))
                candidates=[e for e in edges if e['to_location_id'] not in visited]
                from app.game.world.genesis.formation_v4 import FormationConfigV4
                from app.game.world.genesis.sphere_topology import CellKey
                sector_level=FormationConfigV4().sector_level
                current_cell=CellKey(**json.loads(rows('select genesis_site from locations where id=?',(current,))[0]['genesis_site'])['cell'])
                def leaves_sector(edge):
                    target_cell=CellKey(**json.loads(rows('select genesis_site from locations where id=?',(edge['to_location_id'],))[0]['genesis_site'])['cell'])
                    return target_cell.parent(sector_level)!=current_cell.parent(sector_level)
                candidates.sort(key=lambda edge:not leaves_sector(edge))
                edge=candidates[0]
                moved=action(f'travel_{index}','Vou para '+edge['direction']+'.')
                current=edge['to_location_id'];assert moved['state']['location']['id']==current,moved['mechanical_summary']
                visited.append(current)
                entry=describe(current);entry['route']=json.loads(edge['spatial_contract']);result['journey'].append(entry)
                local=action(f'plants_{index}','Observo a vegetação.',{'kind':'look'})['plant_result']['individuals']
                entry['observed_plants']=len(local)
                assert target['individual_id'] not in {p['individual_id'] for p in local}
            for destination in reversed(visited[:-1]):
                edge=rows('select * from location_connections where from_location_id=? and to_location_id=?',(current,destination))[0]
                moved=action('return_'+destination[-6:],'Vou para '+edge['direction']+'.')
                current=destination;assert moved['state']['location']['id']==current
            revisited=action('inspect_return','Examino a planta.',{'kind':'observe','individual_id':target['individual_id']})
            assert next(p['remaining'] for p in revisited['plant_result']['parts'] if p['part_id']==part['part_id'])==part['remaining']-1
            action('wait','Espero 16 horas.')
            before_restart=action('before_restart','Observo a vegetação.',{'kind':'look'})
            map_before=timed('map','/map-view')
            assert {p['id'] for p in map_before['locations']}==set(visited)
            assert not any(k in json.dumps(map_before) for k in ('from_point','root_point','genesis_site','spatial_contract'))
            process.terminate();process.wait(timeout=15);process=launch()
            resumed=timed('restart_resume','/start',{})
            assert resumed['state']['location']['id']==root
            after=action('after_restart','Observo a vegetação.',{'kind':'look'})
            assert after['plant_result']==before_restart['plant_result']
            assert timed('map_restart','/map-view')==map_before
            result['restart_preserved']=True
            result['locations']=rows('select count(*) n from locations l join regions r on r.id=l.region_id where r.campaign_id=?',(cid,))[0]['n']
            result['persisted_counts']={table:rows('select count(*) n from '+table+' where campaign_id=?',(cid,))[0]['n']
                for table in ('regions','genesis_sphere_sectors','genesis_plant_individuals','genesis_environment_points','genesis_vegetation_communities')}
            result['persisted_counts']['connections']=rows('select count(*) n from location_connections c join locations l on l.id=c.from_location_id join regions r on r.id=l.region_id where r.campaign_id=?',(cid,))[0]['n']
            report['seeds'].append(result)
            print('TP1_HTTP',seed,result['timings_seconds'],flush=True)
    finally:
        process.terminate();process.wait(timeout=15);server_log.close()
        assert original==(hashlib.sha256(normal.read_bytes()).hexdigest() if normal.exists() else None)
        report['normal_database_sha256']=original
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Artifacts:',folder,flush=True)
    return report


if __name__=='__main__':run()
