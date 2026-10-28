"""Explicit climate version dispatch; no fallback or conversion of existing saves."""
from .config import ClimateConfig


def parse_climate_config(data):
    version = data.get("climate_version")
    if type(version) is not int:
        raise ValueError("An explicit integer climate version is required")
    if version == 1:
        return ClimateConfig.model_validate(data)
    if version == 2:
        from .v2 import ClimateConfigV2
        return ClimateConfigV2.model_validate(data)
    if version == 3:
        if 'condensation_profile' in data:
            from .v3 import ClimateConfigV3R1
            return ClimateConfigV3R1.model_validate(data)
        from .v3 import ClimateConfigV3
        return ClimateConfigV3.model_validate(data)
    raise ValueError("Unsupported climate version")
