"""L1 analytic seasonal clock and traits. No per-day or per-visit random rolls."""
import json
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator
from ..terrain.field import checksum

DAY=1440;YEAR=360*DAY;Q=1000000
RARITY={"comum":(5,7),"incomum":(10,14),"raro":(20,30),"muito_raro":(45,60),"excepcional":(90,120)}
GROWTH={"arvore":(600,1800),"arbusto":(120,360),"erva":(20,60),"flor":(20,80),"graminea":(20,90),
    "samambaia":(60,180),"musgo":(90,240),"liquen":(180,540),"fungo":(10,60),"trepadeira":(90,360),
    "junco":(60,180),"alga":(30,120),"consorcio_simbiotico":(90,360)}
PARTIAL={"folhas","petalas","flores","frutos","sementes","esporos","propagulos","ramos","casca","fibras","frondes","fragmentos","fragmento_talo","fragmento_lamina","filamentos"}
SEASONS=((0,60,3),(60,150,0),(150,240,1),(240,330,2),(330,360,3))
NAMES=("primavera","verao","outono","inverno")


class LifeOverride(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid",strict=True)
    recovery_days: int|None=Field(default=None,ge=1,le=10000)
    mature_days: int|None=Field(default=None,ge=10,le=50000)
    reason: str=Field(min_length=8,max_length=512)


class LifeConfigL1(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid",strict=True)
    life_version: Literal[1]=1
    mortality_policy: Literal["partial_tissue_l1"]="partial_tissue_l1"
    overrides: dict[str,LifeOverride]=Field(default_factory=dict)
    automatic_colonization: bool=True
    dispersal_m: int=Field(default=40,ge=5,le=200)
    establishment_days: int=Field(default=14,ge=7,le=180)

    @field_validator("life_version",mode="before")
    @classmethod
    def strict_version(cls,v):
        if type(v) is not int:raise ValueError("Explicit life version required")
        return v


def life_profile(species,config=None):
    config=config or LifeConfigL1();category=species.rarity_name
    if species.magic=="excepcional":category="excepcional"
    if category not in RARITY:raise ValueError("Unknown real catalog rarity; explicit review required")
    lo,hi=GROWTH[species.kind];traits=json.loads(species.growth_json or "{}")
    ref=traits.get("tempo_para_maturidade_dias_referencia_intervalo")
    if ref and max(lo,ref[0])<=min(hi,ref[1]):lo,hi=max(lo,ref[0]),min(hi,ref[1])
    mature=lo+int(checksum([species.id,"L1_maturity"])[:8],16)%(hi-lo+1)
    override=config.overrides.get(species.id)
    if override and override.mature_days:mature=override.mature_days
    times={}
    for p in species.parts():
        a,b=RARITY[category];days=a+int(checksum([species.id,p["id"],species.kind,"L1_recovery"])[:8],16)%(b-a+1)
        o=config.overrides.get(p["id"]) or override
        if o and o.recovery_days:days=o.recovery_days
        if category=="excepcional" and days<90:raise ValueError("Exceptional recovery requires >=90 days and canonical conditions")
        times[p["id"]]=days
    return {"version":1,"rarity":category,"rarity_source":"v22.raridade_not_ecological_rarity_index",
        "recovery_days":times,"mature_active_days":mature,"germination_active_days":min(21,max(3,mature//10)),
        "propagation_strategy":traits.get("estrategia_reprodutiva_proposta","unknown"),
        "growth_seasons":traits.get("estacoes_crescimento_preservadas",list(NAMES)),
        "mortality_policy":"partial_tissue_l1","assumptions":"gameplay_growth_and_abiotic_propagation_not_measured_botany"}


def windows(rates,allowed=None,phase=None):
    result=[]
    for a,b,s in SEASONS:
        if allowed and NAMES[s] not in allowed and "todo_ano_condicionado_a_atividade_biologica" not in allowed:continue
        # Dec/Jan share the same winter phenology, without a discontinuity at year rollover.
        pieces=[(a,b)]
        if phase:
            bounds=((60,105),(150,195),(240,285),(330,375)) if phase=="flowering" else ((105,150),(195,240),(285,330),(15,60))
            pieces=[]
            for x,y in bounds:
                for shift in (-360,0,360):
                    l,h=max(a,x+shift),min(b,y+shift)
                    if l<h:pieces.append((l,h))
        for x,y in pieces:
            if rates[s]>0:result.append((x*DAY,y*DAY,rates[s]))
    return result


def work(start,end,rates,allowed=None,phase=None):
    if end<start:raise ValueError("Ecological time cannot move backwards")
    intervals=windows(rates,allowed,phase)
    annual=sum((b-a)*r for a,b,r in intervals)
    def cumulative(t):
        years,rest=divmod(t,YEAR)
        return years*annual+sum(max(0,min(rest,b)-a)*r for a,b,r in intervals)
    return cumulative(end)-cumulative(start)


def time_for_work(start,amount,rates,allowed=None,phase=None):
    if amount<=0:return start
    annual=work(0,YEAR,rates,allowed,phase)
    if not annual:return None
    lo=start;hi=start+(amount//annual+2)*YEAR
    while lo<hi:
        mid=(lo+hi)//2
        if work(start,mid,rates,allowed,phase)>=amount:hi=mid
        else:lo=mid+1
    return lo


def growth_clock(state):
    """GA1 uses its signed frozen pace; legacy L1 retains its seasonal clock."""
    return state.get('growth_rates_ppm',state['rates']),state['profile']['growth_seasons']


def maturity_minute(state):
    rates,seasons=growth_clock(state)
    return time_for_work(state['birth_minute'],state['profile']['mature_active_days']*DAY*Q,rates,seasons)
