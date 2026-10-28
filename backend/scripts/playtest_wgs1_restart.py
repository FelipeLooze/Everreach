"""Small real-Uvicorn WGS1 persistence smoke; all data lives in a temp SQLite."""
import hashlib, json, os, socket, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

def main():
    backend=Path(__file__).resolve().parents[1]
    real_db=backend/'everreach.db'
    real_hash=hashlib.sha256(real_db.read_bytes()).hexdigest() if real_db.exists() else None
    folder=Path(tempfile.mkdtemp(prefix='everreach-wgs1-'))
    dbpath=folder/'wgs1.sqlite'
    env={**os.environ,'DATABASE_URL':'sqlite:///'+dbpath.as_posix(),'PYTHONIOENCODING':'utf-8'}
    for role in ('INTENT','NARRATIVE','REGENERATION'):
        env[role+'_LLM_PROVIDER']='disabled';env[role+'_LLM_FALLBACK_PROVIDER']='';env[role+'_LLM_FALLBACK_MODEL']=''
    with (folder/'migration.log').open('w') as log:
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=backend,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    def request(path,body=None):
        req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=240) as r:return json.load(r)
        except HTTPError as e:raise AssertionError(f'{path} {e.code}: {e.read().decode()}') from e
    log=(folder/'server.log').open('a')
    def launch():
        p=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=backend,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(180):
            if p.poll() is not None:raise RuntimeError('Uvicorn exited; see '+str(folder))
            try:request('/openapi.json');return p
            except OSError:time.sleep(.25)
        p.terminate();p.wait();raise RuntimeError('Uvicorn startup timeout')
    report={'profile':'world_genesis_ap1_tp1_wgs1_v1','seed':42,'browser':'not used; HTTP server test only','steps':[]}
    process=launch()
    try:
        campaign=request('/api/campaigns',{'name':'WGS1 real restart','world_profile':report['profile'],'world_seed':42})
        cid=campaign['id'];actor=request(f'/api/campaigns/{cid}/characters',{'name':'Exploradora'});aid=actor['id']
        prefix=f'/api/campaigns/{cid}';query=f'?character_id={aid}';n=0
        def action(text,formation=None):
            nonlocal n
            n+=1;body={'text':text,'action_key':f'wgs1-restart-{n}'}
            if formation:body['formation_action']={'kind':formation}
            return request(prefix+'/actions'+query,body)
        started=request(prefix+'/start'+query,{})
        root=started['state']['location']['id']
        action('Exploro os arredores.')
        with sqlite3.connect(dbpath) as con:
            raw=con.execute('select genesis_site from locations where id=?',(root,)).fetchone()[0]
        from app.game.world.genesis.sphere_topology import CellKey, DIRECTIONS, neighbor
        from app.game.world.genesis.local_formations import candidate
        start=CellKey(**json.loads(raw)['cell'])
        def find_path(wanted,max_depth=28):
            from collections import deque
            queue=deque([(start,[])]);seen={start}
            while queue:
                cell,path=queue.popleft()
                if candidate(42,vars(cell))==wanted:return path
                if len(path)>=max_depth:continue
                for direction in DIRECTIONS:
                    nxt=neighbor(cell,direction)
                    if nxt not in seen:seen.add(nxt);queue.append((nxt,path+[(nxt,direction)]))
            raise AssertionError(f'No {wanted} route found within {max_depth} cells')
        def travel_to(archetype):
            path=find_path(archetype)
            for index,(target,_) in enumerate(path):
                if index and index%2==0:action('Eu descanso.')
                action('Olho ao redor.')
                with sqlite3.connect(dbpath) as con:
                    edges=con.execute('select id,to_location_id,direction from location_connections where from_location_id=(select location_id from characters where id=?) and active=1',(aid,)).fetchall()
                    match=None
                    for edge in edges:
                        site=con.execute('select genesis_site from locations where id=?',(edge[1],)).fetchone()
                        if site and json.loads(site[0] or '{}').get('cell')==vars(target):match=edge;break
                if match is None:raise AssertionError('TP1 route edge was not discoverable through normal observation')
                moved=action('Vou para '+match[2]+'.')
                if moved['state']['location']['id']!=match[1]:raise AssertionError('TP1 movement did not reach discovered adjacent cell')
            with sqlite3.connect(dbpath) as con:
                row=con.execute('select f.id,f.location_id,f.data,w.stored_litres from genesis_natural_formations f left join genesis_local_water_bodies w on w.formation_id=f.id where f.campaign_id=? and f.archetype_id=?',(cid,archetype)).fetchone()
            if row is None:raise AssertionError(f'{archetype} was not materialized by TP1')
            site=request(prefix+'/map-view'+query)
            if any(k in json.dumps(site) for k in ('from_point','spatial_contract','genesis_site')):raise AssertionError('Public map leaked hidden physical coordinates')
            return row,path
        def move_to_cell(target):
            action('Olho ao redor.')
            with sqlite3.connect(dbpath) as con:
                current=con.execute('select location_id from characters where id=?',(aid,)).fetchone()[0]
                edges=con.execute('select id,to_location_id,direction from location_connections where from_location_id=? and active=1',(current,)).fetchall()
                edge=next((e for e in edges if (lambda row: row and json.loads(row[0] or '{}').get('cell')==vars(target))(con.execute('select genesis_site from locations where id=?',(e[1],)).fetchone())),None)
            if edge is None:raise AssertionError('Return TP1 edge not found by normal observation')
            action('Vou para '+edge[2]+'.')
        def return_to_root(path):
            for index,target in enumerate([*(cell for cell,_ in reversed(path[:-1])),start]):
                if index and index%2==0:action('Eu descanso.')
                move_to_cell(target)
        spring,spring_path=travel_to('EV-LOC-0068');action('Olho ao redor.')
        with sqlite3.connect(dbpath) as con:current=con.execute('select location_id from characters where id=?',(aid,)).fetchone()[0]
        with sqlite3.connect(dbpath) as con: edge=con.execute('select direction,to_location_id from location_connections where from_location_id=? and active=1 and to_location_id=?',(current,spring[1])).fetchone()
        if not edge:raise AssertionError('Spring access edge not available')
        action('Vou para '+edge[0]+'.');spring_visit=action('Inspeciono a nascente.','inspect')['formation_result']
        action('Olho ao redor.')
        with sqlite3.connect(dbpath) as con:
            current=con.execute('select location_id from characters where id=?',(aid,)).fetchone()[0]
            exit_edge=con.execute('select direction,to_location_id from location_connections where from_location_id=? and direction="exterior" and active=1',(current,)).fetchone()
        if not exit_edge:raise AssertionError('Spring exit missing')
        action('Vou para '+exit_edge[0]+'.');return_to_root(spring_path)
        action('Eu descanso.')
        cave,cave_path=travel_to('EV-LOC-0050');action('Olho ao redor.')
        with sqlite3.connect(dbpath) as con:
            interior_id=json.loads(con.execute('select data from genesis_natural_formations where id=?',(cave[0],)).fetchone()[0])['interior_location_id']
        before_entry=request(prefix+'/map-view'+query)
        if interior_id in {x['id'] for x in before_entry['locations']}:raise AssertionError('Cave interior was visible before entry')
        with sqlite3.connect(dbpath) as con:
            current=con.execute('select location_id from characters where id=?',(aid,)).fetchone()[0]
            outer=con.execute('select direction from location_connections where from_location_id=? and to_location_id=? and active=1',(current,cave[1])).fetchone()
        action('Vou para '+outer[0]+'.')
        invalid=action('Entro na galeria interior.')
        if invalid['state']['location']['type']=='genesis_formation_interior':raise AssertionError('Cave interior entered without discovering/accessing its connection')
        with sqlite3.connect(dbpath) as con:entry=con.execute('select direction,to_location_id from location_connections where from_location_id=? and direction="entrar" and active=1',(cave[1],)).fetchone()
        if not entry:raise AssertionError('Cave entry graph edge missing')
        action('Olho ao redor.');action('Vou para '+entry[0]+'.')
        inside=action('Inspeciono o interior.','inspect')['formation_result']
        action('Olho ao redor.');action('Vou para sair.');after_exit=action('Inspeciono novamente.','inspect')['formation_result']
        if after_exit['features'] != action('Inspeciono novamente.','inspect')['formation_result']['features']:raise AssertionError('Cave revisit changed identity')
        with sqlite3.connect(dbpath) as con:current=con.execute('select location_id from characters where id=?',(aid,)).fetchone()[0]
        before={'spring':spring_visit,'cave':inside,'location':current}
        map_before_restart=request(prefix+'/map-view'+query)
        process.terminate();process.wait(timeout=20);process=launch()
        resumed=request(prefix+'/start'+query,{})
        if resumed['state']['location']['id']!=before['location']:raise AssertionError('Character location not restored after backend restart')
        map_after_restart=request(prefix+'/map-view'+query)
        if map_after_restart!=map_before_restart:raise AssertionError('Map discovery changed across backend restart')
        revisit=action('Inspeciono após reinício.','inspect')['formation_result']
        if not revisit or revisit.get('features')!=after_exit['features']:raise AssertionError('Cave contents/discovery changed after restart')
        with sqlite3.connect(dbpath) as con:
            count=con.execute('select count(*) from genesis_natural_formations where campaign_id=?',(cid,)).fetchone()[0]
            water=con.execute('select stored_litres,revision from genesis_local_water_bodies where campaign_id=?',(cid,)).fetchone()
            interiors=con.execute('select count(*) from locations where type="genesis_formation_interior" and id in (select json_extract(data,"$.interior_location_id") from genesis_natural_formations where campaign_id=?)',(cid,)).fetchone()[0]
            formation=con.execute('select id,location_id,archetype_id from genesis_natural_formations where id=?',(cave[0],)).fetchone()
        if count!=2 or interiors!=1 or water!=(12000,0) or formation!=(cave[0],cave[1],'EV-LOC-0050'):
            raise AssertionError(f'Unexpected persistence counts/identity: {count=} {interiors=} {water=} {formation=}')
        report.update({'campaign_id':cid,'character_id':aid,'visited_spring':True,'entered_cave':True,'exited_cave':True,
            'inspected_after_restart':True,'restart_preserved':True,'formations':count,'cave_interiors':interiors,
            'spring_stock_litres_revision':water,'hidden_coordinates_exposed':False,
            'gameplay_stages':{'candidate':'deterministic_v1_selector','materialized':'persisted_instance','discoverable':'TP1_observe_action',
                'reachable':'discovered_LocationConnection','explorable':'visit_inspect_enter_exit_revisit'}})
    finally:
        process.terminate();process.wait(timeout=20);log.close()
        assert real_hash==(hashlib.sha256(real_db.read_bytes()).hexdigest() if real_db.exists() else None)
        report['temporary_artifacts']=str(folder);(folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
if __name__=='__main__':main()
