"""Consolidate only real matched proof databases, verify checksums and test logs."""
from datetime import datetime,timezone
import argparse,hashlib,json,re,sqlite3
from pathlib import Path

from app.game.world.genesis.vegetation import renewal as l2
from app.game.world.genesis.terrain.field import checksum
from scripts.validate_adventure_renewal import KINDS

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts/vegetation-ga2'
SEEDS=(42,0,7,2026,12345)


def read_only(path):return sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)


def main():
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=OUT)
    OUT=parser.parse_args().out.resolve()
    records={(policy,kind,seed):json.loads((OUT/f'{policy}-{kind}-{seed}.json').read_text(encoding='utf-8'))
             for seed in SEEDS for kind in KINDS for policy in ('L2','GA2')}
    proof_checks=[]
    for seed in SEEDS:
        for kind in KINDS:
            authorities=[];removed=[]
            for policy in ('L2','GA2'):
                stem=f'{policy}-{kind}-{seed}';r=records[policy,kind,seed]
                with read_only(OUT/f'{stem}-initial.sqlite') as db:
                    receipts=[json.loads(row[0]) for row in db.execute("SELECT payload FROM genesis_vegetation_life_events WHERE status='disturbance_applied'")]
                    receipt=next(x for x in receipts if x.get('kind')=='L2_disturbance' and x['request'][1]==r['species_id'])
                    removed.append(receipt['selected_slots'])
                with read_only(OUT/f'{stem}.sqlite') as db:
                    vg=db.execute('SELECT signature FROM genesis_vegetation_plans').fetchone()[0]
                    lp=db.execute('SELECT signature FROM genesis_vegetation_life').fetchone()[0]
                    authorities.append((vg,lp))
                    descriptor,dc,signature=db.execute(f'SELECT descriptor,descriptor_checksum,signature FROM {l2.Plan.__tablename__}').fetchone()
                    assert checksum(json.loads(descriptor))==dc and dc[:24]==signature==r['signature']
                    for data,cs in db.execute(f'SELECT data,data_checksum FROM {l2.Renewing.__tablename__}'):
                        d=json.loads(data);assert checksum(d)==cs;l2.validate(d)
                    for data,cs in db.execute('SELECT data,data_checksum FROM genesis_living_populations'):
                        assert checksum(json.loads(data))==cs
                    established=db.execute("SELECT COUNT(*) FROM genesis_vegetation_life_events WHERE population_id=? AND status='established'",(r['population_id'],)).fetchone()[0]
                    assert established==r['event_states'].get('established',0)
                    for payload,cs in db.execute("SELECT payload,payload_checksum FROM genesis_vegetation_life_events WHERE status='established'"):
                        x=json.loads(payload);assert checksum(x)==cs and x['escrow_mass_mg']>0
                        if x.get('ga2_signature'):assert checksum(x['ga2_child'])==x['ga2_child_checksum']
                proof_checks.append({'seed':seed,'kind':kind,'policy':policy,'signature':signature,'established':established})
            assert authorities[0]==authorities[1],(seed,kind,'physical or GA1 authority differs')
            assert removed[0]==removed[1],(seed,kind,'unmatched physical removals')

    summary={'cases':60,'seeds':list(SEEDS),'matched_physical_removals':True,'same_Vg2_and_GA1_authorities':True,
             'first_birth_ranges':{},'forest_seed42':[],'actual_established_events':{},
             'GA2_body_rows':sorted({r['body_rows'] for (p,k,s),r in records.items() if p=='GA2'})}
    for kind in KINDS:
        summary['first_birth_ranges'][kind]={p:[min(records[p,kind,s]['first_birth_days'] for s in SEEDS),max(records[p,kind,s]['first_birth_days'] for s in SEEDS)] for p in ('L2','GA2')}
    for policy in ('L2','GA2'):
        summary['actual_established_events'][policy]=sum(r['event_states'].get('established',0) for (p,k,s),r in records.items() if p==policy)
    for day in (0,7,15,30,60,90,180):
        row={'day':day}
        for policy in ('L2','GA2'):
            r=records[policy,'large_tree',42];sample=r['snapshots'][str(day)];q=sample['population']
            s=next(p for p in sample['structure']['populations'] if p['species_id']==r['species_id'])
            row[policy]={'living':q['living_count'],'stages':q['stages'],'surviving_founders':s['surviving_founders'],
                         'new_adults':q['stages']['adult']-s['surviving_founders'],'vacancies':q['capacity']-q['living_count'],
                         'cover_percent_patch':s['cover_ppm']/10000,'whole_patch_cover_percent':sample['structure']['cover_ppm']/10000,
                         'mean_height_m':s['mean_height_cm']/100}
        summary['forest_seed42'].append(row)
    (OUT/'measured-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

    lines=['# GA2 — resultados medidos','',
           '60 campanhas isoladas. Geografia, GA1 e posições removidas conferidas nos bancos de cada par. Tempos contados desde a perturbação real.','',
           '| Categoria | Nascimento L2 (dias, min–max) | GA2 (dias, min–max) |','|---|---:|---:|']
    for kind in KINDS:
        a=summary['first_birth_ranges'][kind]
        lines.append(f"| {kind} | {a['L2'][0]:.2f}–{a['L2'][1]:.2f} | {a['GA2'][0]:.0f}–{a['GA2'][1]:.0f} |")
    lines+=['','| Seed | Flores | Ervas | Gramíneas | Arbustos | Árvores comuns | Árvores grandes |','|---|---:|---:|---:|---:|---:|---:|']
    for seed in SEEDS:lines.append('| '+str(seed)+' | '+' | '.join(f"{records['GA2',k,seed]['first_birth_days']:.0f}" for k in KINDS)+' |')
    lines+=['','## Floresta da seed 42','',
            '| Dia | Vivos L2 | Vivos GA2 | Fundadores | Novos adultos | Jovens | Germinando | Vagas | Cobertura da população no patch | Altura média |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in summary['forest_seed42']:
        a=row['GA2'];lines.append(f"| {row['day']} | {row['L2']['living']} | {a['living']} | {a['surviving_founders']} | {a['new_adults']} | {a['stages']['young']} | {a['stages']['germinating']} | {a['vacancies']} | {a['cover_percent_patch']:.4f}% | {a['mean_height_m']:.2f} m |")
    lines+=['','## Primeira oportunidade, produção, nascimento e maturidade GA2','',
            'Maturidade calculada pelo relógio GA1 de descendentes realmente estabelecidos, dentro do período observado.','',
            '| Seed | Categoria | Espécie | Oportunidade (d) | Propágulo (d) | Nascimento (d) | Maturidade (d) |','|---|---|---|---:|---:|---:|---:|']
    for seed in SEEDS:
        for kind in KINDS:
            r=records['GA2',kind,seed];values=[r[k] for k in ('first_opportunity_days','first_propagule_days','first_birth_days','first_maturity_days')]
            lines.append(f"| {seed} | {kind} | {r['species_id']} | "+' | '.join('—' if v is None else f'{v:.2f}' for v in values)+' |')
    benchmark=json.loads((OUT/'benchmark.json').read_text())
    assert len(benchmark)==14 and all(r['revisit_equal'] for r in benchmark)
    lines+=['','## Benchmark independente','',
            '| Salto (dias) | L2 atualização/consulta (s) | GA2 atualização/consulta (s) | GA2 revisita sem avanço (s) |','|---|---:|---:|---:|']
    for day in (30,60,90,180,360,1800,3600):
        rows={r['policy']:r for r in benchmark if r['days']==day}
        lines.append(f"| {day} | {rows['L2']['ecology_query_seconds']:.3f} | {rows['GA2']['ecology_query_seconds']:.3f} | {rows['GA2']['same_time_revisit_seconds']:.3f} |")
    (OUT/'results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

    log_counts={'vegetation-ga2-tests-final.log':19,'vegetation-ga2-integrity-tests.log':2,
                'vegetation-ga2-encounter-test.log':1,'vegetation-ga2-cache-test.log':1,
                'vegetation-ga2-matched-control-tests.log':2,'vegetation-ga2-legacy-regression.log':88,
                'vegetation-ga2-late-registration-tests.log':2}
    logs={}
    for name,n in log_counts.items():
        raw=(ROOT/'artifacts'/name).read_bytes();s=raw.decode('utf-16') if raw.startswith(b'\xff\xfe') else raw.decode('utf-8')
        matches=re.findall(r'(\d+) passed[^\n]*',s);assert matches and int(matches[-1])==n,(name,s[-500:])
        logs[name]={'passed':n,'summary':s.splitlines()[-1]}
    real=ROOT/'backend/everreach.db';stat=real.stat();stamp=datetime.fromtimestamp(stat.st_mtime,timezone.utc).isoformat()
    assert stat.st_size==2027520 and stamp.startswith('2026-10-26T21:53:21')
    with read_only(real) as db:
        exists=db.execute('SELECT name FROM sqlite_master WHERE name=?',(l2.Plan.__tablename__,)).fetchone()
        descriptors=[] if exists is None else [json.loads(x[0]) for x in db.execute(f'SELECT descriptor FROM {l2.Plan.__tablename__}')]
        assert not any(d.get('kind')=='vegetation_renewal_ga2' for d in descriptors)
    flora=ROOT/'datasets/02_Flora/Everreach_Flora_3096_Extremos_Ecologia_v7_2.json'
    sha=hashlib.sha256(flora.read_bytes()).hexdigest();assert sha=='a2d177f65e96ac90b572a6acc78c1513e9a01db40032257a3bbe3d58cf0acb38'
    validation={'policy':'adventure_renewal_ga2','validated_at_utc':datetime.now(timezone.utc).isoformat(),
                'distinct_tests_passed':113,'new_GA2_cases':25,'legacy_cases':88,'logs':logs,
                'count_note':'matched-control run repeats one S1 regression; late-registration run repeats one prior GA2 case; neither counted twice',
                'matched_pair_checks':30,'persistent_campaigns':60,'proofs':proof_checks,
                'flora_sha256':sha,'real_save':{'read_only_check':True,'bytes':stat.st_size,'mtime_utc':stamp,'GA2_activated':False},
                'benchmark_cases':14,'images':['large_tree-comparison.png','flor-comparison.png'],
                'scope':'affected systems only, not every repository test'}
    (OUT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    print('Validated 60 persistent proofs, 30 identical-removal pairs, 113 distinct tests and unchanged real save.',flush=True)


if __name__=='__main__':main()
