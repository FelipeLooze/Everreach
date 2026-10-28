"""Offline audit of frozen C2 and E1. No database, calibration or save writes."""
import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import json
from math import asin, degrees, pi
from pathlib import Path
import time

from app.game.world.genesis.climate.calibration import report as native_report
from app.game.world.genesis.climate.geometry import Q, geometry
from app.game.world.genesis.climate.plan import _solve_climate
from app.game.world.genesis.climate.query import sample_climate
from app.game.world.genesis.climate.v2 import ClimateConfigV2
from app.game.world.genesis.environment.preview import color, continuous, fonts
from app.game.world.genesis.formation_config import plate_scale_m
from app.game.world.genesis.sphere_area import cell_solid_angle
from app.game.world.genesis.sphere_topology import CellKey, cell_center
from app.game.world.genesis.terrain.field import checksum
from scripts.validate_environment import environment_inputs

ROOT = Path(__file__).resolve().parents[2]
SEEDS = (42, 0, 7, 2026, 12345)


@lru_cache(maxsize=1)
def forest_ids():
    from app.game.world.genesis.environment.catalog import load_environment_catalog
    return frozenset(k for k,v in load_environment_catalog()['natural'].items() if v['grupo']=='florestas')


def weighted_quantile(values, fraction):
    """Left weighted quantile; values are diagnostic (value, solid angle) pairs."""
    if not values:
        return None
    ordered = sorted(values)
    target = sum(w for _, w in ordered) * fraction
    running = 0
    for value, weight in ordered:
        running += weight
        if running >= target:
            return value
    return ordered[-1][0]


class Distribution:
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)

    def result(self):
        area = sum(r['solid_angle'] for r in self.rows)
        result = {'sample_count': len(self.rows), 'solid_angle': area}
        if not area:
            return result
        for field in ('rain_mm', 'temperature_c', 'pet_mm', 'P_over_PET'):
            pairs = [(r[field], r['solid_angle']) for r in self.rows if r[field] is not None]
            defined = sum(w for _, w in pairs)
            result[field] = {'defined_area_fraction': defined/area,
                'mean': sum(v*w for v, w in pairs)/defined if defined else None,
                'quantiles_05_25_50_75_95': [weighted_quantile(pairs, q) for q in (.05, .25, .5, .75, .95)]}
        result['ratio_of_area_mean_P_to_area_mean_PET'] = (
            result['rain_mm']['mean']/result['pet_mm']['mean'] if result['pet_mm']['mean'] else None)
        indices = Counter(); environments = Counter(); states = Counter(); eligible = Counter()
        for r in self.rows:
            w = r['solid_angle'];p = r['P_over_PET']
            category = ('energy_limited' if p is None else 'humid' if p >= 1 else
                'moderate_deficit' if p >= .5 else 'semiarid' if p >= .2 else 'arid' if p >= .05 else 'hyperarid')
            indices[category] += w
            environments[r['primary_potential'] or 'unclassified'] += w
            for k, v in r['states'].items():
                states[k] += w*v
            for identifier in r['eligible']:
                eligible[identifier] += w
        result['index_area_fractions'] = {k: v/area for k, v in indices.items()}
        result['primary_area_fractions'] = {k: v/area for k, v in environments.items()}
        result['eligible_area_fractions_overlapping'] = {k: v/area for k, v in eligible.items()}
        result['natural_state_area_fractions'] = {k: v/(100*area) for k, v in states.items()}
        result['dry_primary_area_fraction'] = sum(v for k, v in environments.items() if 'DESERTO' in k or k == 'EV-BIO-ESTEPE')/area
        result['ecotone_area_fraction'] = sum(r['solid_angle'] for r in self.rows if r['ecotone'])/area
        result['any_forest_eligible_area_fraction'] = sum(r['solid_angle'] for r in self.rows if forest_ids().intersection(r['eligible']))/area
        result['forest_primary_area_fraction'] = sum(r['solid_angle'] for r in self.rows if r['primary_potential'] in forest_ids())/area
        result['humid_warm_area_fraction'] = sum(r['solid_angle'] for r in self.rows if r['P_over_PET'] is not None and r['P_over_PET']>=1 and r['temperature_c']>=5)/area
        result['humid_warm_sample_count'] = sum(r['P_over_PET'] is not None and r['P_over_PET']>=1 and r['temperature_c']>=5 for r in self.rows)
        result['humid_warm_without_forest_eligible_sample_count'] = sum(r['P_over_PET'] is not None and r['P_over_PET']>=1 and r['temperature_c']>=5
            and not forest_ids().intersection(r['eligible']) for r in self.rows)
        result['dry_primary_with_forest_eligible_area_fraction'] = sum(r['solid_angle'] for r in self.rows
            if ('DESERTO' in (r['primary_potential'] or '') or r['primary_potential']=='EV-BIO-ESTEPE') and forest_ids().intersection(r['eligible']))/area
        result['mean_height_m'] = sum(r['height_m']*r['solid_angle'] for r in self.rows)/area if all('height_m' in r for r in self.rows) else None
        result['dry_primary_with_P_over_PET_ge_0_5_area_fraction'] = sum(r['solid_angle'] for r in self.rows
            if r['P_over_PET'] is not None and r['P_over_PET']>=.5 and
            ('DESERTO' in (r['primary_potential'] or '') or r['primary_potential']=='EV-BIO-ESTEPE'))/area
        result['period_mean_rain_mm'] = [sum(r['period_rain_mm'][s]*r['solid_angle'] for r in self.rows)/area for s in range(4)]
        result['period_mean_temperature_c'] = [sum(r['period_temperature_c'][s]*r['solid_angle'] for r in self.rows)/area for s in range(4)]
        return result


def grouping_keys(row):
    surface = 'land' if row['land'] else 'below_reference_datum'
    lat = abs(row['latitude_degrees'])
    band = next(label for limit, label in ((15, '00-15'), (30, '15-30'), (45, '30-45'),
        (60, '45-60'), (75, '60-75'), (91, '75-90')) if lat < limit)
    keys = ['global', 'surface/'+surface, 'latitude/'+surface+'/'+band]
    if not row['land']:
        keys.append('surface/reference_ocean' if row['reference_ocean'] else 'surface/disconnected_below_datum')
    else:
        distance = row['ocean_distance_m']
        zone = ('unknown' if distance is None else '0-1000km' if distance < 1000000 else
            '1000-3000km' if distance < 3000000 else '3000-10000km' if distance < 10000000 else '10000km+')
        keys.append('ocean_distance/'+zone)
        keys.append('relief/mountain_context' if row['mountain'] else 'relief/other_land')
        height = row['height_m']
        keys.append('altitude/'+('0-500m' if height < 500 else '500-1500m' if height < 1500 else '1500-3000m' if height < 3000 else '3000m+'))
    return keys


def point_record(sampler, key):
    point = cell_center(key)
    env = sampler.sample(point);f = env['logical_facts'];physical = env['physical_inputs']
    climate = sample_climate(sampler.climate, point, _terrain_height=physical['T1_height_mm']//1000)
    # Exact bridge checks: no climatological quantity is rounded a second time in E1.
    assert f['clima.precipitacao_anual_mm'] == sum(s['precipitation_mm'] for s in climate['seasons']) == climate['annual_precipitation_mm']
    assert f['clima.temperatura_media_anual_c'] == climate['mean_temperature_centi_c']/100
    ratio = climate['precipitation_to_pet_ppm']
    assert f['clima.indice_aridez'] == (ratio/Q if ratio is not None else None)
    assert physical[f'C{sampler.climate.config.climate_version}_seasons'] == climate['seasons']
    assert climate['annual_potential_evapotranspiration_mm'] == sum(s['potential_evapotranspiration_mm'] for s in climate['seasons'])
    return {'point': list(point.xyz), 'cell': [key.face, key.level, key.x, key.y],
        'solid_angle': cell_solid_angle(key),
        'latitude_degrees': degrees(asin(max(-1, min(1, point.xyz[2]/sum(v*v for v in point.xyz)**.5)))),
        'land': f['terreno.evidencia_superficie_continental'], 'reference_ocean': physical['reference_ocean_H1'],
        'mountain': f['terreno.contexto_relevo_montanhoso'], 'height_m': f['terreno.altitude_m'],
        'ocean_distance_m': physical['ocean_distance_m'], 'continentality_ppm': physical['continentality_ppm'],
        'rain_mm': climate['annual_precipitation_mm'], 'temperature_c': climate['mean_temperature_centi_c']/100,
        'pet_mm': climate['annual_potential_evapotranspiration_mm'], 'P_over_PET': f['clima.indice_aridez'],
        'period_rain_mm': [s['precipitation_mm'] for s in climate['seasons']],
        'period_temperature_c': [s['temperature_centi_c']/100 for s in climate['seasons']],
        'primary_potential': env['primary_potential'], 'ecotone': env['ecotone'],
        'states': dict(Counter(r['state'] for r in env['results'])),
        'eligible': [r['environment_id'] for r in env['results'] if r['state'] == 'elegivel']}


def sample_grid(sampler, level):
    groups = defaultdict(Distribution);rows = []
    for face in range(6):
        for y in range(2**level):
            for x in range(2**level):
                r = point_record(sampler, CellKey(face, level, x, y));rows.append(r)
                for key in grouping_keys(r):groups[key].add(r)
    assert abs(sum(r['solid_angle'] for r in rows)-4*pi) < 1e-10
    return rows, {k: v.result() for k, v in sorted(groups.items())}


def summarize_rows(rows):
    groups=defaultdict(Distribution)
    for row in rows:
        for key in grouping_keys(row):groups[key].add(row)
    return {k:v.result() for k,v in sorted(groups.items())}


def write_maps(rows, level, seed, path, *, climate_label='C2'):
    from PIL import Image, ImageDraw
    n = 2**level
    image = Image.new('RGB', (1530, 1450), '#101e29');draw = ImageDraw.Draw(image);font, small = fonts()
    draw.text((20, 18), f'{climate_label} / E1 climate audit / seed {seed} / R=63710 km / {len(rows)} area-weighted probes', fill='white', font=font)
    titles = ('Annual precipitation mm: blue=0, red=3000', 'Mean temperature C: blue=-40, red=35',
        'P/PET: blue=0, red=2; grey=undefined PET', 'E1 potential only; marine reference dark blue; unknown land grey')
    for panel, title in enumerate(titles):
        y0 = 85+panel*280;draw.text((20, y0), title, fill='white', font=small)
        for face in range(6):
            tile = Image.new('RGB', (n, n));px = tile.load()
            for y in range(n):
                for x in range(n):
                    r = rows[face*n*n+y*n+x]
                    if panel == 0:c = continuous(r['rain_mm'], 0, 3000)
                    elif panel == 1:c = continuous(r['temperature_c'], -40, 35)
                    elif panel == 2:c = continuous(r['P_over_PET'], 0, 2)
                    else:c = color(r['primary_potential']) if r['land'] else (27, 68, 111)
                    px[x,y] = c
            image.paste(tile.resize((225,225), Image.Resampling.NEAREST), (20+250*face,y0+25))
            draw.text((25+250*face,y0+30), str(face), fill='white', font=small)
    from app.game.world.genesis.environment.catalog import load_environment_catalog
    catalog = load_environment_catalog()
    identifiers = sorted({r['primary_potential'] for r in rows if r['primary_potential']})
    for i, identifier in enumerate(identifiers):
        x = 20+(i%4)*375;y = 1220+(i//4)*27
        draw.rectangle((x,y,x+12,y+12), fill=color(identifier))
        draw.text((x+20,y),catalog['natural'][identifier]['nome'],fill='white',font=small)
    draw.text((20,1420),'Offline climate potential; no flora, runoff, permanent water, geography edits or campaign migration.',fill='#d9b780',font=small)
    image.save(path)


def ablations(plan):
    """One-factor experiments, diagnostic only; none becomes an authoritative preset."""
    rows = []
    for name, changes in (
        ('replay', {}), ('64_iterations', {'transport_iterations':64}),
        ('no_orographic_condensation', {'orographic_condensation_ppm_per_km':0}),
        ('double_moisture_length', {'moisture_length_m':plan.moisture_length_m*2}),
        ('negligible_distance_loss', {'moisture_length_m':10**12}),
        ('no_extratropical_ascent', {'extratropical_condensation_ppm':0})):
        cfg = ClimateConfigV2(**{**plan.config.model_dump(), **changes})
        alternate = _solve_climate(plan.source_signature,plan.hydrology_signature,plan.radius_m,plan.sea_level_m,
            plan.heights,plan.marine,plate_scale_m(plan.radius_m),cfg)
        if not changes:assert alternate == plan
        r = native_report(alternate)
        rows.append({'experiment':name,'overrides':changes,'diagnostic_only':True,
            'land':r['groups']['surface/land'],'ocean':r['groups'].get('surface/reference_ocean'),
            'residual_ppm':list(alternate.transport_residual_ppm)})
    return rows


def fixed_geography_radius_controls(plan):
    """Counterfactual graph experiments, not save-compatible alternate worlds.

    Hold angular ocean mask and height samples fixed, changing only physical link
    lengths and the existing automatic length policy. No plans are persisted.
    """
    rows=[]
    for radius in (6371000,63710000,637100000,10**12):
        alternate=_solve_climate(plan.source_signature,plan.hydrology_signature,radius,plan.sea_level_m,
            plan.heights,plan.marine,plate_scale_m(radius),plan.config)
        result=native_report(alternate)
        rows.append({'radius_m':radius,'diagnostic_only_not_a_world_snapshot':True,
            'fixed_inputs':'same angular heights and ocean mask; default length policy',
            'moisture_length_m':alternate.moisture_length_m,'maritime_length_m':alternate.maritime_length_m,
            'land':result['groups']['surface/land']})
    return rows


def write_profiles(cases,path):
    from PIL import Image,ImageDraw
    image=Image.new('RGB',(1450,700),'#101e29');draw=ImageDraw.Draw(image);font,small=fonts()
    draw.text((20,18),'C2 / E1: area-weighted LAND precipitation, mm/year / R=63710 km',font=font,fill='white')
    latitude=('00-15','15-30','30-45','45-60','60-75','75-90')
    distance=('0-1000km','1000-3000km','3000-10000km','10000km+')
    draw.text((120,65),'Absolute latitude (degrees)',font=small,fill='white')
    draw.text((850,65),'C2 ocean distance (coarse proxy)',font=small,fill='white')
    for i,label in enumerate(latitude+distance):
        x=120+i*120 if i<6 else 850+(i-6)*145
        draw.text((x,95),label,font=small,fill='white')
    for y,case in enumerate(cases):
        yy=140+y*85;draw.text((20,yy+14),str(case['seed']),font=font,fill='white')
        groups=case['grids'][max(case['grids'],key=int)]['groups']
        for i,key in enumerate(tuple('latitude/land/'+s for s in latitude)+tuple('ocean_distance/'+s for s in distance)):
            x=120+i*120 if i<6 else 850+(i-6)*145
            value=groups.get(key,{}).get('rain_mm',{}).get('mean')
            draw.rectangle((x,yy,x+(110 if i<6 else 135),yy+60),fill=continuous(value,0,1000))
            draw.text((x+8,yy+8),'unknown' if value is None else f'{value:.0f}',font=font,fill='white')
            draw.text((x+8,yy+35),f"n={groups.get(key,{}).get('sample_count',0)}",font=small,fill='white')
    draw.text((20,615),'Colors: blue=0, red=1000 mm. Values are area-weighted means; n is probe count.',font=small,fill='white')
    draw.text((20,650),'Coastal bins are not resolved shorelines. No runoff or vegetation is inferred from these values.',font=small,fill='#d9b780')
    image.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/climate-audit-after-e1')
    parser.add_argument('--seeds',type=int,nargs='+',default=list(SEEDS))
    parser.add_argument('--fine-level',type=int,choices=(4,5),default=5)
    args = parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    records = []
    for seed in args.seeds:
        start = time.perf_counter();sampler = environment_inputs(seed,63710000)
        before = checksum(sampler.climate.to_dict()),checksum(sampler.regional.macro.to_dict()),checksum(sampler.regional.terrain.plan.source.to_dict())
        folder = args.output/f'seed-{seed}';folder.mkdir(exist_ok=True)
        grids = {}
        for level in (3,args.fine_level):
            started = time.perf_counter();rows,groups = sample_grid(sampler,level)
            grids[str(level)] = {'samples':len(rows),'groups':groups,'seconds':time.perf_counter()-started}
            (folder/f'samples-level-{level}.json').write_text(json.dumps(rows,separators=(',',':')),encoding='utf-8')
            if level == args.fine_level:
                write_maps(rows,level,seed,folder/'climate-environments.png')
                warm = [r for r in rows if r['land'] and r['temperature_c']>=5 and r['P_over_PET'] is not None]
                witnesses = {'wet_warm':max(warm,key=lambda r:(r['P_over_PET'],r['rain_mm'])) if warm else None,
                    'dry_warm':min(warm,key=lambda r:(r['P_over_PET'],-r['temperature_c'])) if warm else None}
        native = native_report(sampler.climate)
        result = {'seed':seed,'radius_m':63710000,'climate_signature':sampler.climate.signature,
            'environment_signature':sampler.signature,'area_method':'exact_cell_solid_angle_with_center_samples',
            'grids':grids,'native_vertex_report':native,'witnesses':witnesses,
            'sources_unchanged':before == (checksum(sampler.climate.to_dict()),checksum(sampler.regional.macro.to_dict()),checksum(sampler.regional.terrain.plan.source.to_dict())),
            'seconds':time.perf_counter()-start,'bridge_mismatches':0}
        if seed == 42:
            result['ablations'] = ablations(sampler.climate)
            result['radius_fixed_geography_controls'] = fixed_geography_radius_controls(sampler.climate)
            result['radius_controls'] = []
            for radius in (6371000,637100000,10**12):
                control = environment_inputs(42,radius).climate
                r = native_report(control)
                result['radius_controls'].append({'radius_m':radius,'signature':control.signature,
                    'maritime_length_m':control.maritime_length_m,'moisture_length_m':control.moisture_length_m,
                    'land':r['groups']['surface/land'],'transport_audit':r['transport_audit']})
        (folder/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8');records.append(result)
        land = grids[str(args.fine_level)]['groups']['surface/land']
        print(json.dumps({'seed':seed,'rain_mm':land['rain_mm']['mean'],'dry_primary_fraction':land['dry_primary_area_fraction'],
            'humid_fraction':land['index_area_fractions'].get('humid',0),'seconds':result['seconds']}),flush=True)
    (args.output/'suite.json').write_text(json.dumps({'cases':records,'source_edits':False,'real_database_opened':False,
        'authoritative_version_changed':False,'diagnostic_only':True},indent=2),encoding='utf-8')
    write_profiles(records,args.output/'latitude-distance.png')


if __name__ == '__main__':
    main()
