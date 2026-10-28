"""Versioned C3/W1 boundary. Atmospheric return is diagnostic, never a water credit.

Gross precipitation + total PET is the surface forcing. W1 actual ET remains
limited by accessible water. The prescribed atmospheric return is not a prior
debit from W1, nor a guaranteed actual ET flux; these are uncoupled climatologies.
"""
from dataclasses import dataclass
from .config import C3_FORCING_CONTRACT
from .plan import WaterPlan,checksum
from ..climate.geometry import Q,interpolate,stencil
from ..climate.query import sample_climate
from ..hydrology.geometry import geometry


@dataclass(frozen=True)
class WaterPlanC3(WaterPlan):
    climate_payload_checksum: str
    atmospheric_recycling_mm: tuple
    atmospheric_net_deposition_mm: tuple

    def to_dict(self):
        return {**super().to_dict(),'forcing_contract':C3_FORCING_CONTRACT,
            'climate_payload_checksum':self.climate_payload_checksum,
            'atmospheric_recycling_mm':self.atmospheric_recycling_mm,
            'atmospheric_net_deposition_mm':self.atmospheric_net_deposition_mm,
            'atmospheric_return_is_actual_W1_ET':False,'atmospheric_return_credited_to_stocks':False}


def project_recycling(climate,h1):
    """Same bilinear weights and mm rounding as C3 gross precipitation.

    PET caps in the atmospheric ledger refer to native climate columns. H1 may
    adjust temperature at a different height. Do not pretend this projection is
    actual local ET or silently clamp its historical diagnostic to H1 PET.
    """
    native=[]
    for s,records in enumerate(climate.accounting):
        native.append(tuple(r[4]*climate.flux_reference_length_m*climate.config.rain_scale_milli_mm_per_day*climate.config.year_days//
            (Q*4000*climate.transport_span_m[s][i]) for i,r in enumerate(records)))
    weights=[stencil(p,climate.config.level) for p in geometry(h1.config.level).points]
    return tuple(tuple(interpolate(native[s],w) for w in weights) for s in range(4))


def attach(plan,climate):
    recycled=project_recycling(climate,plan.hydrology)
    net=tuple(tuple(p-r for p,r in zip(ps,rs)) for ps,rs in zip(plan.precipitation_mm,recycled))
    return WaterPlanC3(**{k:getattr(plan,k) for k in WaterPlan.__dataclass_fields__},
        climate_payload_checksum=checksum(climate.to_dict()),atmospheric_recycling_mm=recycled,atmospheric_net_deposition_mm=net)


def validate_diagnostics(plan):
    n=len(plan.hydrology.heights)
    if (not isinstance(plan,WaterPlanC3) or not isinstance(plan.climate_payload_checksum,str) or len(plan.climate_payload_checksum)!=64 or
            any(len(v)!=4 or any(len(p)!=n for p in v) for v in (plan.atmospheric_recycling_mm,plan.atmospheric_net_deposition_mm))):
        raise ValueError('W1 C3 diagnostics/source checksum missing or malformed')
    for season in range(4):
        for p,r,net in zip(plan.precipitation_mm[season],plan.atmospheric_recycling_mm[season],plan.atmospheric_net_deposition_mm[season]):
            if type(r) is not int or type(net) is not int or not 0<=r<=p or net!=p-r:
                raise ValueError('W1 C3 atmospheric diagnostic partition mismatch')


def load(data,base,climate):
    expected=attach(base,climate)
    if (data.get('forcing_contract')!=C3_FORCING_CONTRACT or data.get('climate_payload_checksum')!=expected.climate_payload_checksum or
            data.get('atmospheric_return_is_actual_W1_ET') is not False or data.get('atmospheric_return_credited_to_stocks') is not False or
            tuple(tuple(s) for s in data.get('atmospheric_recycling_mm',()))!=expected.atmospheric_recycling_mm or
            tuple(tuple(s) for s in data.get('atmospheric_net_deposition_mm',()))!=expected.atmospheric_net_deposition_mm):
        raise ValueError('W1 C3 pinned atmospheric diagnostics differ from climate source')
    # Recheck forcing, not the hydrological solve: changing only signatures must
    # never turn an old C2 balance into a valid C3 balance.
    for i,point in enumerate(geometry(base.hydrology.config.level).points):
        sample=sample_climate(climate,point,_terrain_height=base.hydrology.heights[i])
        for s,period in enumerate(sample['seasons']):
            if (base.precipitation_mm[s][i]!=period['precipitation_mm'] or base.pet_mm[s][i]!=period['potential_evapotranspiration_mm'] or
                    base.snowfall_mm[s][i]!=period['snowfall_potential_mm'] or base.temperatures_centi_c[s][i]!=period['temperature_centi_c']):
                raise ValueError('W1 C3 surface forcing differs from the pinned climate')
    validate_diagnostics(expected)
    return expected
