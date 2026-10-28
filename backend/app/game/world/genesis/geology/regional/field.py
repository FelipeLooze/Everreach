"""JR1 physical histories; no query-time fabrication of adapter evidence."""
from collections import OrderedDict
from copy import deepcopy
from ..field import substrate
from .config import RegionalConfig
from .spatial import PhysicalSites
from ...terrain.field import checksum

FACIES = {6:(6,9),7:(7,9,10),8:(8,9,7),9:(9,8,7),10:(10,7,9),
          11:(11,13),12:(12,13),13:(13,11),14:(14,13,11),3:(3,15),15:(15,3),2:(2,4),4:(4,2),5:(5,4)}


class RegionalSampler:
    def __init__(self,macro,terrain,config=None):
        self.macro,self.terrain = macro,terrain
        self.config = config or RegionalConfig()
        self.descriptor = {"kind":"regional_geology_jr1","regional_version":1,
            "j1_signature":macro.signature,"j1_checksum":macro.data["checksum"],
            "terrain_signature":terrain.plan.signature,"config":self.config.model_dump(),
            "radius_m":macro.data["radius_m"]}
        self.signature = checksum(self.descriptor)[:24]
        self.sites = PhysicalSites(macro.data["radius_m"],self.config.formation_spacing_m,self.signature)
        self.cache = OrderedDict()
        self.formation_builds = 0

    def address(self,point):
        parent = self.macro.unit_at(point)
        key,center = self.sites.nearest(point)
        identifier = "jr1:"+checksum([self.signature,parent["geological_unit_id"],key])[:32]
        return parent,key,center,identifier

    def formation(self,point):
        parent,key,center,identifier = self.address(point)
        if identifier in self.cache:
            self.cache.move_to_end(identifier)
            return deepcopy(self.cache[identifier])
        data = self._build(parent,key,center,identifier)
        self.formation_builds += 1
        self.cache[identifier] = data
        while len(self.cache)>256:
            self.cache.popitem(last=False)
        return deepcopy(data)

    def _build(self,parent,key,center,identifier):
        n = int(checksum([self.signature,"formation",identifier])[:32],16)
        original = int(parent["substrates"][0][-3:])
        kinds = {h["kind"] for h in parent["history"]}
        facies = FACIES.get(original,(original,))
        number = facies[n%len(facies)]
        thermal = "intrusive_thermal_episode" in kinds or original==1
        intrusive = thermal and (n>>8)%4==0
        if intrusive and original==1:
            number = 4  # subordinate mafic intrusive stock, backed by J1 history
        sediment = "ancient_basin_deposition" in kinds and "regional_metamorphism" not in kinds
        history = [{"kind":"inherited_J1_context","parent_id":parent["geological_unit_id"],
                    "parent_checksum":checksum(parent),"history_kinds":sorted(kinds)},
                   {"kind":"regional_facies","substrate":substrate(number),"parent_host":substrate(original),
                    "rule":"JR1 compatible facies/strata within fixed J1 context"}]
        length = self.sites.spacing*(2000+(n>>16)%6001)//10000
        thickness = 80+(n>>32)%721
        cover = int((n>>48)%241)-40
        depth_index = min(95,18+thickness//20+max(0,cover)//12)
        if sediment:
            history.append({"kind":"regional_stratigraphy","layers":[
                {"substrate":substrate(number),"thickness_m":thickness},
                {"substrate":parent["substrates"][0],"thickness_m":thickness//2}],
                "source":"J1 ancient basin; no present-day water inferred"})
        if thermal:
            history.append({"kind":"regional_intrusive_body" if intrusive else "regional_thermal_host",
                "parent_process":"intrusive_thermal_episode" if "intrusive_thermal_episode" in kinds else "crust_assembly",
                "thickness_m":thickness})
        fracture = "fracture_network" in kinds or (thermal and (n>>64)%4!=0)
        circulation = thermal and fracture and (n>>72)%5<3
        diagenesis = sediment and number in (6,8,9) and parent["tectonic_source"]["plate_age_myr"]>=100
        if fracture:
            history.append({"kind":"regional_fracture_structure","length_m":length,
                "cause":"inherited_tectonic_fractures" if "fracture_network" in kinds else "thermal_contraction"})
        if circulation:
            history.append({"kind":"regional_mineralizing_circulation","length_m":length,
                "heat":"J1 compatible thermal body","permeability":"regional_fracture_structure",
                "fluid":"ancient_magmatic_not_W1_or_C2"})
        if diagenesis:
            history.append({"kind":"regional_diagenetic_horizon","length_m":length,"thickness_m":max(1,thickness//20),
                "host":substrate(number),"cause":"ancient_J1_basin_compaction_and_facies"})
        evidence = {}
        def add(flag,kind):
            evidence[flag] = {"authority":"JR1","history_kind":kind}
        if sediment:
            add("ambiente_deposicional_confirmado","regional_stratigraphy")
        if fracture:
            add("fraturas_mapeadas","regional_fracture_structure")
        if circulation:
            for flag in ("circulacao_mineralizante_confirmada","processo_mineralizante_confirmado","concentracao_mineralizante_confirmada"):
                add(flag,"regional_mineralizing_circulation")
            if number in (1,3,11,13,14,15):
                for flag in ("veio_aurifero_primario","processo_aurifero_profundo"):
                    add(flag,"regional_mineralizing_circulation")
            add("mineralizacao_argentifera_profunda","regional_mineralizing_circulation")
            if "volcanic_sequence" in kinds:
                add("alteracao_hidrotermal_em_unidade_vulcanica","regional_mineralizing_circulation")
        if diagenesis:
            add("concentracao_mineralizante_confirmada","regional_diagenetic_horizon")
            if number in (8,9):
                add("horizonte_ferrifero_confirmado","regional_diagenetic_horizon")
            if number==6:
                add("mineralizacao_plumbifera_sedimentar","regional_diagenetic_horizon")
        if "volcanic_sequence" in kinds:
            history.append({"kind":"inherited_volcanic_sequence","parent_id":parent["geological_unit_id"]})
            add("historico_vulcanico_persistente","inherited_volcanic_sequence")
        if thickness+max(0,cover)>=800 and thermal:
            history.append({"kind":"regional_deep_geometry","thickness_m":thickness,"cover_m":cover})
            add("unidade_geologica_profunda","regional_deep_geometry")
        baseline = self.terrain.sample(center)
        anchor_inside = self.macro.unit_at(center)["geological_unit_id"]==parent["geological_unit_id"]
        terrestrial = baseline["height_mm"]>self.terrain.plan.source.config.sea_level_m*1000
        history.append({"kind":"regional_cover_geometry","signed_top_depth_m":cover,
            "meaning":"static_model_relative_to_T1_baseline_not_current_access_or_climate_erosion"})
        return {"kind":"regional_formation_jr1","regional_version":1,"authority_signature":self.signature,
            "formation_id":identifier,"geological_unit_id":identifier,"formation_opportunity_id":"formation:"+identifier,
            "parent_unit_id":parent["geological_unit_id"],"geological_region_id":parent["geological_region_id"],
            "physical_address":list(key),"anchor_point":list(center.xyz),"anchor_inside_parent":anchor_inside,
            "contact_fragment_pending":not anchor_inside,"substrates":[substrate(number)],
            "history":history,"evidence_records":evidence,"structure_length_m":length,
            "thickness_m":thickness,"signed_top_depth_m":cover,"depth_index_0_100":depth_index,
            "exposure":{"rock_outcrop_model":cover<=0 and terrestrial,"anchor_terrestrial_baseline":terrestrial,
                "terrain_height_mm":baseline["height_mm"],"slope_proxy_ppm":baseline["slope_proxy_ppm"],
                "source":"JR1 cover + unchanged T1 baseline","current_exposure_confirmed":False,"access_authorized":False},
            "terrain_modified":False,"canonical_authorizations":[],"event_instance_ids":[]}


def adapt_formation(formation,world_id):
    kinds = {h["kind"] for h in formation["history"]}
    if type(formation["regional_version"]) is not int or formation["regional_version"]!=1 or any(r["authority"]!="JR1" or r["history_kind"] not in kinds for r in formation["evidence_records"].values()):
        raise ValueError("JR1 evidence lacks recorded physical history")
    return {"adapter_version":"JR1-1","world_id":world_id,"region_id":formation["geological_region_id"],
        "geological_unit_id":formation["formation_id"],"formation_opportunity_id":formation["formation_opportunity_id"],
        "lithology_substrate_ids":formation["substrates"],"evidence_flags":sorted(formation["evidence_records"]),
        "depth_index_0_100":formation["depth_index_0_100"],"canonical_authorizations":[],
        "event_instance_ids":[],"source_lineage_ids":[],"evidence_provenance":formation["evidence_records"]}
