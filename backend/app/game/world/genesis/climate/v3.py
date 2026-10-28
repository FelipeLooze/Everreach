"""Experimental C3: distance-based optical depth and rain-limited bare-ground recycling.

The upwind averaging graph is not a globally conservative air-mass solver. The
ledger is exact in integer humidity indices per link, not in planetary litres.
"""
from dataclasses import dataclass
from math import isqrt
from typing import Literal
from functools import lru_cache
from pydantic import Field
from .v2 import ClimateConfigV2, condensation as c2_condensation
from .geometry import Q, geometry
from .physics import (declinations, lapse, ocean_distances, seasonal_temperature,
                      wind, pet_milli_mm_day)
from .plan import ClimatePlan, signature, validate


class ClimateConfigV3(ClimateConfigV2):
    climate_version: Literal[3] = 3
    transport_iterations: int = Field(default=64, ge=8, le=128)
    land_recycling_ppm: int = Field(default=450000, ge=0, le=650000)
    # Both lengths have a physical meaning and remain pinned configuration.
    condensation_length_m: int | None = Field(default=None, ge=1, le=10**12)
    flux_reference_length_m: int | None = Field(default=None, ge=1, le=10**12)


class ClimateConfigV3R1(ClimateConfigV3):
    """Explicit calibration profile; no additional fields in legacy C3 dumps."""
    condensation_profile: Literal['fraction_hazard_r1']='fraction_hazard_r1'


@lru_cache(maxsize=4096)
def fraction_optical_depth(fraction):
    """-ln(1-f), using a fixed integer atanh series, f <= 0.85.

    Rates that describe a fractional loss need this conversion before they can
    serve as optical depths. 32 terms at 1e12 internal precision suffice here.
    """
    if type(fraction) is not int or not 0<=fraction<=850000:
        raise ValueError('Fraction outside calibrated optical-depth domain')
    scale=10**12;x=fraction*scale//(2*Q-fraction)
    square=x*x//scale;term=x;total=0
    for k in range(32):
        total+=term//(2*k+1);term=term*square//scale
    return 2*total*Q//scale


def exp_negative(tau):
    """Fixed integer Padé [2/2] with scaling/squaring; no authoritative libm."""
    if tau <= 0:return Q
    if tau >= 20*Q:return 0
    shifts=0
    while tau>Q//4:
        tau=(tau+1)//2;shifts+=1
    value=(12*Q*Q-6*tau*Q+tau*tau)*Q//(12*Q*Q+6*tau*Q+tau*tau)
    for _ in range(shifts):value=value*value//Q
    return value


def rain_fraction(direction,declination,rise_m,span_m,length_m,config):
    base=c2_condensation(direction,declination,0,config)
    oro=config.orographic_condensation_ppm_per_km
    if isinstance(config,ClimateConfigV3R1):
        base=fraction_optical_depth(base)
        oro=fraction_optical_depth(oro)
    tau=base*span_m//length_m+max(0,rise_m)*oro//1000
    return Q-exp_negative(tau)


def recycled_transport(stencils,retention,fractions,source,pet_caps,iterations,recycle_ppm,*,node_order=None):
    n=len(source);order=tuple(range(n)) if node_order is None else tuple(node_order)
    if sorted(order)!=list(range(n)) or not 0<=recycle_ppm<=650000:
        raise ValueError('Invalid C3 iteration order or recycling limit')
    previous=list(source);ledger=None
    for _ in range(iterations):
        current=[0]*n;ledger=[None]*n
        for i in order:
            pairs=stencils[i]
            incoming=sum(previous[j]*w for j,w in pairs)//sum(w for _,w in pairs)
            available=source[i] if source[i] else incoming*retention[i]//Q
            gross=available*fractions[i]//Q
            recycled=0 if source[i] else min(gross*recycle_ppm//Q,pet_caps[i])
            outgoing=source[i] if source[i] else available-gross+recycled
            current[i]=outgoing
            # Ocean reservoirs are prescribed boundary conditions, not conserved columns.
            ledger[i]=(incoming,0 if source[i] else incoming-available,available,gross,recycled,outgoing,pet_caps[i])
        residual=max(abs(a-b) for a,b in zip(current,previous));previous=current
    return tuple(previous),tuple(ledger),residual


@dataclass(frozen=True)
class ClimatePlanV3(ClimatePlan):
    condensation_length_m: int
    flux_reference_length_m: int
    transport_span_m: tuple
    accounting: tuple


def solve(source_signature,h1_signature,radius,sea,heights,marine,plate_length,config):
    g=geometry(config.level)
    maritime_length=config.maritime_length_m or max(1,plate_length//3)
    moisture_length=config.moisture_length_m or max(1,2*plate_length)
    condensation_length=config.condensation_length_m or max(1,plate_length//4)
    reference=config.flux_reference_length_m or max(1,plate_length//4)
    lengths={tuple(sorted((i,j))):max(1,isqrt(sum((a-b)**2 for a,b in zip(g.directions[i],g.directions[j])))*radius//Q)
        for i in range(len(g.points)) for j in g.adjacent[i] if i<j}
    distances=ocean_distances(g.adjacent,lengths,marine)
    maritime=tuple(0 if d is None else Q*maritime_length**2//(maritime_length+d)**2 for d in distances)
    forcing=[seasonal_temperature(d,m,config) for d,m in zip(g.directions,maritime)]
    sea_t=tuple(tuple(f[0][s] for f in forcing) for s in range(4))
    solar=tuple(tuple(f[1][s] for f in forcing) for s in range(4))
    all_rain=[];all_moisture=[];all_wind=[];residuals=[];all_ledger=[];all_spans=[]
    for s,declination in enumerate(declinations(config)):
        winds=tuple(wind(d,declination,config) for d in g.directions)
        stencils=[];retention=[];fractions=[];source=[];pet_caps=[];spans=[]
        for i,adjacent in enumerate(g.adjacent):
            pairs=[]
            for j in adjacent:
                delta=tuple(b-a for a,b in zip(g.directions[i],g.directions[j]))
                score=max(0,-sum(a*b for a,b in zip(delta,winds[i])))*Q//max(1,isqrt(sum(a*a for a in delta)))
                if score:pairs.append((j,score))
            pairs=tuple(pairs or ((j,1) for j in adjacent));stencils.append(pairs)
            total=sum(w for _,w in pairs)
            span=sum(lengths[tuple(sorted((i,j)))]*w for j,w in pairs)//total;spans.append(span)
            upstream=sum(heights[j]*w for j,w in pairs)//total
            retention.append(exp_negative(span*Q//moisture_length))
            fractions.append(rain_fraction(g.directions[i],declination,max(0,heights[i]-upstream),span,condensation_length,config))
            temperature=lapse(sea_t[s][i],heights[i]-sea,config)
            supply=min(Q,max(150000,250000+max(0,temperature+1000)*150)) if marine[i] else 0
            if temperature<0:supply=supply*max(100000,Q+temperature*200)//Q
            source.append(supply)
            # The same flux/step conversion is used in both rain and PET caps.
            pet_caps.append(pet_milli_mm_day(temperature,solar[s][i],config)*Q*span//(config.rain_scale_milli_mm_per_day*reference)
                if config.rain_scale_milli_mm_per_day else 0)
        moisture,ledger,residual=recycled_transport(stencils,retention,fractions,source,pet_caps,config.transport_iterations,config.land_recycling_ppm)
        all_rain.append(tuple(r[3]*reference*config.rain_scale_milli_mm_per_day*config.year_days//(Q*4000*span) for r,span in zip(ledger,spans)))
        all_moisture.append(moisture);all_wind.append(winds);residuals.append(residual);all_ledger.append(ledger);all_spans.append(tuple(spans))
    plan=ClimatePlanV3(config,source_signature,h1_signature,signature(source_signature,h1_signature,config),radius,sea,
        maritime_length,moisture_length,tuple(heights),tuple(marine),distances,maritime,sea_t,solar,tuple(all_rain),
        tuple(all_moisture),tuple(all_wind),tuple(residuals),condensation_length,reference,tuple(all_spans),tuple(all_ledger))
    validate(plan);validate_accounting(plan)
    return plan


def validate_accounting(plan):
    from ..formation_config import plate_scale_m
    n=len(plan.heights)
    expected_length=max(1,plate_scale_m(plan.radius_m)//4)
    if (type(plan.condensation_length_m) is not int or type(plan.flux_reference_length_m) is not int or
            plan.condensation_length_m!=(plan.config.condensation_length_m or expected_length) or
            plan.flux_reference_length_m!=(plan.config.flux_reference_length_m or expected_length) or len(plan.accounting)!=4 or
            len(plan.transport_span_m)!=4 or any(len(s)!=n for s in plan.accounting+plan.transport_span_m)):
        raise ValueError('Invalid C3 accounting dimensions')
    for s,records in enumerate(plan.accounting):
        for i,r in enumerate(records):
            if len(r)!=7 or any(type(v) is not int or v<0 for v in r):raise ValueError('Invalid C3 ledger')
            incoming,loss,available,gross,recycled,outgoing,cap=r
            span=plan.transport_span_m[s][i]
            if type(span) is not int or span<=0 or max(incoming,available,gross,outgoing)>Q or gross>available:
                raise ValueError('C3 humidity/span bounds violated')
            temperature=lapse(plan.sea_temperature_centi_c[s][i],plan.heights[i]-plan.sea_level_m,plan.config)
            expected_cap=pet_milli_mm_day(temperature,plan.insolation_ppm[s][i],plan.config)*Q*span//(plan.config.rain_scale_milli_mm_per_day*plan.flux_reference_length_m) if plan.config.rain_scale_milli_mm_per_day else 0
            if cap!=expected_cap or recycled>min(gross*plan.config.land_recycling_ppm//Q,cap) or outgoing!=plan.moisture_ppm[s][i]:
                raise ValueError('C3 recycling budget violated')
            if not plan.marine[i] and (incoming!=loss+available or available+recycled!=gross+outgoing or
                    available!=incoming*exp_negative(span*Q//plan.moisture_length_m)//Q or
                    recycled!=min(gross*plan.config.land_recycling_ppm//Q,cap)):
                raise ValueError('C3 local atmospheric accounting mismatch')
            if plan.marine[i] and recycled:raise ValueError('C3 ocean cannot recycle terrestrial water')
            expected=gross*plan.flux_reference_length_m*plan.config.rain_scale_milli_mm_per_day*plan.config.year_days//(Q*4000*span)
            if plan.precipitation_mm[s][i]!=expected:raise ValueError('C3 rain/ledger mismatch')


def load(data,base):
    plan=ClimatePlanV3(**{k:getattr(base,k) for k in ClimatePlan.__dataclass_fields__},
        condensation_length_m=data['condensation_length_m'],flux_reference_length_m=data['flux_reference_length_m'],
        transport_span_m=tuple(tuple(s) for s in data['transport_span_m']),
        accounting=tuple(tuple(tuple(r) for r in s) for s in data['accounting']))
    validate_accounting(plan)
    return plan


def accounting_summary(plan):
    from .calibration import area_weights
    weights=area_weights(plan.config.level);area=sum(w for w,m in zip(weights,plan.marine) if not m)
    gross=recycled=0.0
    for s,records in enumerate(plan.accounting):
        for i,r in enumerate(records):
            if plan.marine[i]:continue
            scale=plan.flux_reference_length_m*plan.config.rain_scale_milli_mm_per_day*plan.config.year_days/(Q*4000*plan.transport_span_m[s][i])
            gross+=weights[i]*r[3]*scale;recycled+=weights[i]*r[4]*scale
    return {'scope':'non_ocean_nodes_including_disconnected_below_datum; area_weighted_climatological_flux_proxy',
        'gross_precipitation_mm':gross/area if area else 0,'recycled_mm':recycled/area if area else 0,
        'net_atmospheric_deposition_mm':(gross-recycled)/area if area else 0,
        'maximum_recycle_fraction_ppm':plan.config.land_recycling_ppm,'local_index_ledger_valid':True,
        'global_mass_conservation_claimed':False,'water_storage_created':False,'vegetation_input':False}
