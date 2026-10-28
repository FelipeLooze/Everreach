"""GA1 opt-in calendar-paced growth; L1 recovery and finite resources stay intact.

This is a game pacing rule, not measured botany or an extra source of water.
It changes no habitat eligibility, birth quota, propagation route or adult stock.
"""
from typing import Literal

from pydantic import Field, field_validator

from .life_math import LifeConfigL1, NAMES, Q, life_profile
from ..terrain.field import checksum


DEFAULT_BANDS = {
    'flower_herb': [3, 7], 'shrub': [7, 15], 'tree': [15, 30],
    'large_tree': [30, 60], 'slow_tree': [60, 120], 'other': [7, 30],
}


class LifeConfigGA1(LifeConfigL1):
    growth_policy: Literal['adventure_calendar_ga1'] = 'adventure_calendar_ga1'
    bands_days: dict[str, list[int]] = Field(default_factory=lambda: {
        key: list(value) for key, value in DEFAULT_BANDS.items()})
    tree_pacing: dict[str, Literal['tree', 'large_tree', 'slow_tree', 'legacy']] = Field(default_factory=dict)
    large_tree_height_cm: int = Field(default=3000, ge=500, le=100000)
    minimum_rate_ppm: int = Field(default=850000, ge=500000, le=1000000)
    seasonal_bonus_ppm: int = Field(default=200000, ge=0, le=250000)
    individual_variation_ppm: int = Field(default=50000, ge=0, le=100000)

    @field_validator('bands_days')
    @classmethod
    def valid_bands(cls, value):
        if set(value) != set(DEFAULT_BANDS):
            raise ValueError('All explicit GA1 pacing classes are required')
        for band in value.values():
            if len(band) != 2 or any(type(x) is not int for x in band) or not 1 <= band[0] <= band[1] <= 50000:
                raise ValueError('Invalid GA1 calendar-day band')
        return value


def parse_config(data):
    """Old descriptors are parsed by exactly the original L1 schema."""
    return (LifeConfigGA1 if 'growth_policy' in data else LifeConfigL1).model_validate(data)


def rules():
    return {
        'policy': 'adventure_calendar_ga1', 'revision': 1,
        'time': 'game_calendar_days_since_established_birth',
        'season': 'bounded_bonus_not_zero_activity_gate',
        'rarity_changes_maturity': False,
        'exceptional': 'legacy_until_explicit_canonical_design',
        'parts_recovery': 'unchanged_L1_seasonal_recovery',
        'habitat_capacity_reproduction': 'unchanged',
        'size_class': 'catalog_mature_height_upper_bound_else_common_tree',
        'slow_class': 'explicit_reviewed_species_assignment_not_rarity',
    }


def pacing_class(sp, cfg):
    if sp.magic == 'excepcional':
        return 'legacy'
    if sp.kind == 'arvore':
        if sp.id in cfg.tree_pacing:
            return cfg.tree_pacing[sp.id]
        return 'large_tree' if sp.height_cm and sp.height_cm[1] >= cfg.large_tree_height_cm else 'tree'
    if sp.kind in ('flor', 'erva', 'graminea'):
        return 'flower_herb'
    return 'shrub' if sp.kind == 'arbusto' else 'other'


def attach_profile(sp, cfg, baseline, environmental_rates):
    profile = life_profile(sp, cfg)
    if not isinstance(cfg, LifeConfigGA1):
        return profile, None
    kind = pacing_class(sp, cfg)
    if kind == 'legacy':
        return profile, None
    lo, hi = cfg.bands_days[kind]
    days = lo + int(checksum([sp.id, 'GA1_maturity'])[:8], 16) % (hi - lo + 1)
    override = cfg.overrides.get(sp.id)
    if override and override.mature_days:
        days = override.mature_days
    preferred = list(profile['growth_seasons'])
    spread = cfg.individual_variation_ppm
    variation = int(checksum([baseline['individual_id'], 'GA1_pace'])[:8], 16) % (2 * spread + 1) - spread
    rates = []
    for i, season in enumerate(NAMES):
        bonus = cfg.seasonal_bonus_ppm if season in preferred or 'todo_ano_condicionado_a_atividade_biologica' in preferred else 0
        rate = cfg.minimum_rate_ppm + bonus * max(0, min(Q, environmental_rates[i])) // Q
        rates.append(max(1, rate * (Q + variation) // Q))
    profile.update(
        growth_policy='adventure_calendar_ga1', pacing_class=kind,
        mature_active_days=days, germination_active_days=min(3, max(1, days // 5)),
        growth_seasons=list(NAMES), preferred_catalog_seasons=preferred,
        maturity_unit='bounded_calendar_day_equivalent',
        assumptions='explicit_fantasy_gameplay_pacing_not_botanical_or_water_budget_evidence',
    )
    return profile, rates
