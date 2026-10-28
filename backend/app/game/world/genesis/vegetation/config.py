from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator


class VegetationConfig(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid",strict=True)
    vegetation_version: Literal[1]=1
    policy: Literal["ecological_v1","exploration_mosaic_v1"]="ecological_v1"
    founding: Literal["pre_player_biogeographic_history_v1"]="pre_player_biogeographic_history_v1"
    patch_spacing_m: int=Field(default=1000,ge=100,le=10000)
    # Representation budget per physical patch, never a world biodiversity quota.
    species_budget: int=Field(default=12,ge=4,le=32)
    broad_range_m: int=Field(default=640000,ge=20000,le=10000000)
    mosaic_m: int=Field(default=4000,ge=500,le=64000)

    @field_validator("vegetation_version",mode="before")
    @classmethod
    def explicit_version(cls,value):
        if type(value) is not int:raise ValueError("An integer vegetation version is required")
        return value


# Explicit game architecture for legacy records with unknown height; not a dataset edit.
TYPE_HEIGHT_CM={"arvore":(800,2400),"arbusto":(40,260),"flor":(8,70),"erva":(10,90),
    "graminea":(15,140),"musgo":(1,9),"liquen":(1,5),"fungo":(2,30),
    "samambaia":(20,180),"junco":(30,220),"trepadeira":(30,400),"alga":(1,50),"consorcio_simbiotico":(1,4)}


class PartCalibrationV1(BaseModel):
    """Operator-reviewed measurements, never inferred from an item's name or price."""
    model_config=ConfigDict(frozen=True,extra="forbid",strict=True)
    species_id: str
    part_id: str
    organism_type: str
    max_mature_units: int=Field(ge=0,le=10000)
    unit_mass_mg: int=Field(gt=0,le=1000000000)
    # The legacy inventory exposes generic weight units, not an enforced kg unit.
    # Require an explicit reviewed conversion instead of silently redefining it.
    inventory_mg_per_weight_unit: int=Field(gt=0,le=10**12)
    tissue_pool_id: str=Field(min_length=5,max_length=128)
    available_tissue_mass_mg: int=Field(gt=0,le=10**12)
    removable_fraction_ppm: int=Field(ge=0,le=1000000)
    evidence_ref: str=Field(min_length=8,max_length=512)
    method: str=Field(min_length=8,max_length=512)
    status: Literal["reviewed_experimental"]

    @model_validator(mode="after")
    def bounded_by_tissue(self):
        if self.max_mature_units*self.unit_mass_mg>self.available_tissue_mass_mg*self.removable_fraction_ppm//1000000:
            raise ValueError("Calibrated yield exceeds the reviewed removable tissue budget")
        return self


class VegetationConfigV2(VegetationConfig):
    vegetation_version: Literal[2]=2
    policy: Literal["regional_canopy_v2","regional_canopy_wgs2_microhabitat_v1",
                    "regional_canopy_wgs2_canonical_v1"]="regional_canopy_v2"
    community_spacing_m: int=Field(default=32000,ge=8000,le=256000)
    structure_wavelength_m: int=Field(default=48000,ge=8000,le=512000)
    resource_calibrations: tuple[PartCalibrationV1,...]=()


def parse_vegetation_config(data):
    if type(data.get("vegetation_version")) is not int:raise ValueError("Explicit vegetation version required")
    if data["vegetation_version"]==2:
        # JSON arrays become immutable tuples at the persistence boundary only.
        d=dict(data);d["resource_calibrations"]=tuple(PartCalibrationV1.model_validate(x) for x in d.get("resource_calibrations",()))
        return VegetationConfigV2.model_validate(d)
    return VegetationConfig.model_validate(data)


def make_vegetation_sampler(environment,water,config=None):
    if isinstance(config,VegetationConfigV2):
        from .v2 import VegetationSamplerV2
        return VegetationSamplerV2(environment,water,config)
    from .field import VegetationSampler
    return VegetationSampler(environment,water,config)
