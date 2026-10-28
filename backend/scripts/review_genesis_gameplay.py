"""GA1 proof on real persisted L2 births, never synthetic seedlings or real saves."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db import models
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.game.time.clock import advance_world_time
from app.game.world.genesis.vegetation import lifecycle as life, renewal as l2, resources, sexual
from app.game.world.genesis.vegetation.growth_gameplay import LifeConfigGA1
from app.game.world.genesis.vegetation.life_math import DAY, LifeConfigL1, maturity_minute
from app.game.world.genesis.vegetation.recovery_structure import measure_community
from scripts.prove_vegetation import prepare
from scripts.validate_plant_resources import actual_individual, inputs


def setup(db, v, kind, seed, config):
    cid = prepare(db, v)
    resources.initialize_resources(db, cid, experimental=True)
    point, parent, part = actual_individual(db, cid, v, seed, kind)
    life.initialize_life(db, cid, config, experimental=True)
    l2.initialize_renewal(db, cid, experimental=True)
    sexual.initialize_sexual_policy(db, cid, experimental=True)
    return cid, point, parent, part


def run(seed, kind, policy, out):
    dest = out / f'{policy}-{kind}-{seed}.json'
    if dest.exists():
        return json.loads(dest.read_text(encoding='utf-8'))
    v = inputs(seed)
    engine = create_engine('sqlite:///:memory:')
    event.listen(engine, 'connect', enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    config = LifeConfigGA1() if policy == 'GA1' else LifeConfigL1()
    with Session(engine) as db:
        started = time.perf_counter()
        cid, point, parent, _ = setup(db, v, kind, seed, config)
        sid = parent.baseline['species_id']
        community = db.get(life.Community, (cid, parent.community_id))
        population = next(p for p in community.baseline['populations'] if p['species_id'] == sid)
        removed = min(150, population['founder_count'] // 2)
        if kind == 'arvore' and seed == 42:
            removed = 700
        original = measure_community(db, cid, community.community_id, v=v, original=True)
        receipt = l2.disturb_population(db, cid, community.community_id, sid, removed, 'gameplay-review', experimental=True)
        t0 = life.now(db, cid)
        child = None
        # Canonical rounds, actual finite banks, physical habitat and real event execution.
        for day in (30, 120, 210, 300, 390, 480):
            if t0 + day * DAY > life.now(db, cid):
                advance_world_time(db, cid, t0 + day * DAY - life.now(db, cid))
            l2.query_population(db, cid, community.community_id, sid)
            pending = db.query(life.Event).filter_by(campaign_id=cid, population_id=population['population_id'], status='pending').order_by(life.Event.due_minute, life.Event.event_id).first()
            if pending is not None:
                advance_world_time(db, cid, pending.due_minute - life.now(db, cid))
                l2.query_population(db, cid, community.community_id, sid)
                child = db.get(life.Individual, (cid, pending.payload['child_id']))
                if child is not None:
                    break
        if child is None:
            raise AssertionError(f'No real established {kind} at seed {seed}, policy {policy}')
        birth = child.state['life']['birth_minute']
        # A first real birth is observed at its due time, not backdated or recreated.
        assert life.now(db, cid) == birth
        initial = deepcopy(child.state)
        records = []
        for day in (7, 15, 30, 60):
            advance_world_time(db, cid, birth + day * DAY - life.now(db, cid))
            life.sync(db, cid, child, v)
            state = child.state
            pure = life.project(child.baseline, initial, life.now(db, cid), v.catalog.species[sid])
            assert state == pure
            life.validate(child.baseline, state)
            q = l2.query_population(db, cid, community.community_id, sid)
            structure = measure_community(db, cid, community.community_id, v=v, advance=False)
            records.append({'days_since_birth': day, 'days_since_disturbance': (life.now(db,cid)-t0)/DAY,
                            'height_cm': state['life']['height_cm'], 'adult_height_cm': child.baseline['height_cm'],
                            'maturity': state['life']['maturity'], 'mature_stock_units': sum(state['part_stock'].values()),
                            'population_living': q['living_count'], 'population_stages': q['stages'],
                            'structure': structure})
        p = life.header(db, cid, v)
        result = {'seed': seed, 'kind': kind, 'policy': policy, 'species_id': sid, 'name': v.catalog.species[sid].name,
                  'life_signature': p.signature, 'config': p.descriptor['config'],
                  'child_id': child.individual_id, 'birth_event_id': child.baseline['birth_event_id'],
                  'original': original, 'capacity': population['founder_count'], 'removals': removed,
                  'birth_wait_calendar_days': (birth-t0)/DAY,
                  'calendar_days_birth_to_adult': (maturity_minute(initial['life'])-birth)/DAY,
                  'profile': initial['life']['profile'], 'growth_rates': initial['life'].get('growth_rates_ppm', initial['life']['rates']),
                  'snapshots': records, 'seconds_including_setup': time.perf_counter()-started,
                  'removed_founder_slots_preserved': receipt.payload['selected_slots'], 'real_campaign_modified': False}
        db.commit()
        raw = engine.raw_connection()
        with sqlite3.connect(out/f'{policy}-{kind}-{seed}.sqlite') as target:
            raw.driver_connection.backup(target)
        raw.close()
        dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    engine.dispose()
    return result


def figure(out, records):
    from PIL import Image, ImageDraw
    from scripts.preview_vegetation import font
    fig = Image.new('RGB', (1400, 900), '#f4f1e8')
    d = ImageDraw.Draw(fig)
    d.text((30, 20), 'EVERREACH | L1 x GA1 | individuos nascidos de propagulos finitos', font=font(25), fill='#22352f')
    d.text((30, 60), 'Altura relativa ao porte adulto; dias contados desde o nascimento real, nao desde o corte.', font=font(17), fill='#22352f')
    for i, kind in enumerate(('flor','erva','arbusto','arvore')):
        x, y = 35+(i%2)*690, 115+(i//2)*350
        items = {r['policy']: r for r in records if r['kind']==kind and r['seed']==42}
        d.text((x,y), f"{kind} | {items['GA1']['species_id']}", font=font(21), fill='#22352f')
        for k, day in enumerate((7,15,30,60)):
            yy = y+45+k*58
            d.text((x,yy), f'{day}d', font=font(16), fill='#22352f')
            for j, policy in enumerate(('L1','GA1')):
                s = items[policy]['snapshots'][k];h=s['height_cm']/s['adult_height_cm']
                row = yy+j*21
                d.rectangle((x+65,row,x+425,row+16),fill='#d9d5cd')
                d.rectangle((x+65,row,x+65+360*h,row+16),fill='#477e62' if j else '#9c7b55')
                d.text((x+435,row-3),f"{policy}: {100*h:.1f}% ({s['maturity']})",font=font(13),fill='#22352f')
        wait=items['GA1']['birth_wait_calendar_days']
        d.text((x,y+290),f'Espera ate primeiro nascimento GA1: {wait:.1f}d; cadencia L2 permanece.',font=font(14),fill='#22352f')
    d.text((30,855),'Politica experimental assinada. Sem alteracao de clima, agua, Vg2, estoques adultos ou campanhas reais.',font=font(17),fill='#22352f')
    fig.save(out/'growth-comparison.png')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,default=Path('../artifacts/genesis-gameplay-review'))
    p.add_argument('--seeds',type=int,nargs='+',default=[42])
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);records=[]
    for seed in a.seeds:
        for kind in ('flor','erva','arbusto','arvore'):
            for policy in ('L1','GA1'):
                r=run(seed,kind,policy,a.out);records.append(r)
                print(seed,kind,policy,'mature_days',round(r['calendar_days_birth_to_adult'],2),'birth_wait_days',round(r['birth_wait_calendar_days'],2),'seconds',round(r['seconds_including_setup'],3),flush=True)
    if 42 in a.seeds:figure(a.out,records)
    (a.out/'summary.json').write_text(json.dumps([{
        k:r[k] for k in ('seed','kind','policy','species_id','name','calendar_days_birth_to_adult','birth_wait_calendar_days','seconds_including_setup')
    } for r in records],ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
