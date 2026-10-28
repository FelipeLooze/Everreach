"""Experimental budget proposal; no historical D14 intensities are read."""
from dataclasses import dataclass
from .adapter import adapt_unit, evaluate_opportunities
from .catalog import load_catalog
from ..terrain.field import checksum

# Per million geological units/material; proposed only for disposable experiments.
RATES = {"comum": 10_000, "incomum": 3_000, "raro": 500, "muito_raro": 0, "lendario": 0}
WORLD_CAPS = {"comum": 4, "incomum": 2, "raro": 1, "muito_raro": 0, "lendario": 0}


@dataclass(frozen=True)
class ExperimentalCalibration:
    version: int = 1
    rate_factor_ppm: int = 1_000_000

    def __post_init__(self):
        if type(self.version) is not int or self.version != 1 or type(self.rate_factor_ppm) is not int or not 0 <= self.rate_factor_ppm <= 2_000_000:
            raise ValueError("Unsupported experimental J1 calibration")


def select_test_deposits(plan, calibration=None):
    """Rank the entire bounded province universe, so quotas never depend on visits."""
    calibration = calibration or ExperimentalCalibration()
    catalog = load_catalog()
    opportunities = [o for unit in plan.units for o in evaluate_opportunities(adapt_unit(unit, plan.signature), catalog)["opportunities"]]
    pools = {}
    for opportunity in opportunities:
        rarity = opportunity["rarity"]
        material = catalog["materials"][opportunity["material_id"]]
        if (rarity == "lendario" or material["origem_condicional"]["exige_autorizacao_canonica_para_fonte_anomala"] or
                material["ocorrencia_geologica_v4"]["formacao_de_fonte"]["requer_condicao_canonica_excepcional"]):
            continue
        ticket = int(checksum(["J1-calibration-1", plan.signature, opportunity["opportunity_id"]])[:16], 16)
        threshold = RATES[rarity]*calibration.rate_factor_ppm//1_000_000
        if ticket*1_000_000 < threshold*2**64:
            pools.setdefault(opportunity["material_id"], []).append((ticket, opportunity))
    selected = []
    units = {u["geological_unit_id"]:u for u in plan.units}
    for material_id, pool in sorted(pools.items()):
        regional = set()
        total = 0
        for _, opportunity in sorted(pool, key=lambda p: (p[0], p[1]["opportunity_id"])):
            if total >= WORLD_CAPS[opportunity["rarity"]]:
                break
            if opportunity["region_id"] in regional:
                continue  # one source/material/geological region
            regional.add(opportunity["region_id"])
            total += 1
            material = catalog["materials"][material_id]
            lo, hi = material["ocorrencia_geologica_v4"]["geometria_e_disponibilidade"]["volume_deposito_referencia_intervalo_unidades_abstratas"]
            volume = lo+int(checksum([opportunity["opportunity_id"], "finite-volume"])[:16], 16)%(hi-lo+1)
            unit = units[opportunity["geological_unit_id"]]
            selected.append({**opportunity, "deposit_id": "deposit:"+checksum(["J1-test", plan.signature, opportunity["opportunity_id"]])[:32],
                "initial_volume_units": volume, "volume_unit": "D14_abstract_not_liters_or_kg",
                "anchor_surface_point":unit["center"], "depth_index_0_100":unit["depth_index_0_100"],
                "access_or_exposure_authorized":False,
                "calibration": {"version": 1, "rate_factor_ppm": calibration.rate_factor_ppm},
                "experimental_only": True, "canonical_exception": False})
    return selected
