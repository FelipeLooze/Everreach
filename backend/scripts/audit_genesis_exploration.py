"""Offline 50-km structural routes: no new locations, water bodies or discoveries."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

from app.game.world.genesis.vegetation.diagnostics import route_diagnostics, structure
from app.game.world.genesis.geology.regional.experiment import window_point
from scripts.validate_plant_resources import inputs
from scripts.validate_vegetation import centers


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--seeds',type=int,nargs='+',default=[42,0,7,2026,12345])
    p.add_argument('--out',type=Path,default=Path('../artifacts/genesis-gameplay-review'))
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);records=[]
    for seed in a.seeds:
        start=time.perf_counter();v=inputs(seed);cold=time.perf_counter()-start
        for name,center in centers(seed).items():
            points=[window_point(center,(i-10)*2500,0,v.radius) for i in range(21)]
            start=time.perf_counter();samples=[v.sample(q) for q in points];elapsed=time.perf_counter()-start
            start=time.perf_counter();reverse=[v.sample(q) for q in reversed(points)];revisit=time.perf_counter()-start
            assert samples==list(reversed(reverse))
            species={p['species_id'] for s in samples for p in s['populations']}
            rare=sorted(sid for sid in species if v.catalog.species[sid].rarity_name in ('raro','muito_raro'))
            r={'seed':seed,'region':name,'cold_world_context_seconds':cold,'sample_seconds':elapsed,
               'reverse_revisit_seconds':revisit, 'states_equal_on_reverse_revisit':True,
               'diagnostic':route_diagnostics(samples,50000),'established_species':len(species),
               'rare_species_in_actual_populations':rare,
               'samples':[{'point':list(q.xyz),'community_id':s['community_id'],**structure(s)} for q,s in zip(points,samples)],
               'scope':'technical_surface_vegetation_sample_not_playable_location_or_water_feature_census',
               'public_map_export':False}
            records.append(r);print(seed,name,json.dumps(r['diagnostic']),flush=True)
        (a.out/'exploration-50km.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    from PIL import Image,ImageDraw
    from scripts.preview_vegetation import font
    palette={'dense_forest':'#21513b','open_forest':'#4f7954','woodland':'#88a066','savanna_mosaic':'#b9aa58',
             'grass_forb_field':'#809a4b','steppe':'#b2a675','shrubland':'#a08e55',
             'cryptogam_cover':'#7b9996','polar_alpine_cover':'#b1c7c8','sparse_desert_vegetation':'#cfb179','barren':'#ccc4b4'}
    height=180+len(records)*55+len(palette)*25
    fig=Image.new('RGB',(1250,height),'#f4f1e8');d=ImageDraw.Draw(fig)
    d.text((25,20),'EVERREACH | percursos tecnicos de 50 km | estrutura visual atual',font=font(24),fill='#22352f')
    d.text((25,60),'21 amostras por percurso; cores sao fisionomias, nao IDs. Nao prova locais jogaveis ou hidrografia.',font=font(16),fill='#22352f')
    for i,r in enumerate(records):
        y=110+i*55;d.text((25,y),f"{r['seed']} / {r['region']}",font=font(16),fill='#22352f')
        for j,s in enumerate(r['samples']):d.rectangle((225+j*39,y,262+j*39,y+30),fill=palette.get(s['form'],'#cc55cc'))
        d.text((1060,y),f"{r['diagnostic']['form_changes']} trocas",font=font(14),fill='#22352f')
    y=130+len(records)*55
    for label,color in palette.items():
        d.rectangle((30,y,50,y+17),fill=color);d.text((65,y-3),label,font=font(16),fill='#22352f');y+=25
    fig.save(a.out/'exploration-50km.png')


if __name__=='__main__':main()
