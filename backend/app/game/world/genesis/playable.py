"""AP1: explicit, bounded adapter from existing authorities to the normal game.

No imports from proof scripts or snapshots. Caller owns the transaction.
The expedition provisions are gameplay rules of this opt-in profile, not flora data.
"""
from time import perf_counter
from types import SimpleNamespace

from app.db.models.campaign import Campaign
from app.db.models.region import Region
from app.db.models.location import Location
from app.db.models.skill import Skill, CharacterSkill
from app.core.enums import (ItemType, ItemInstanceMode, ItemLocationType, ItemOwnerType,
                            ToolCapability, EventType, EquipmentSlot)
from app.services.event_log import log_event
from .formation_v4 import FormationConfigV4
from .sphere_topology import SurfacePoint, cell_at, cell_center
from .formation_plan import indexed_cell
from .service import initialize_world, materialize_sector
from .terrain.config import TerrainConfig
from .terrain.service import initialize_terrain, get_terrain_sampler
from .hydrology.config import HydrologyConfig
from .hydrology.service import initialize_hydrology, get_hydrology_plan
from .hydrology.regional import RegionalHydrologyConfig
from .hydrology.regional_service import initialize_regional_hydrology
from .climate.v3 import ClimateConfigV3R1
from .climate.service import initialize_climate
from .water.config import WaterConfigC3R155
from .water.service import initialize_water_balance
from .hydro_geometry.config import G1Config
from .hydro_geometry.service import initialize_geometry
from .water_reconciliation.config import ReconciliationConfig
from .water_reconciliation.service import initialize_reconciliation
from .water_reconciliation.practical.config import PracticalConfig
from .water_reconciliation.practical.service import initialize_practical_hydrology
from .geology.config import GeologyConfig
from .geology.service import initialize_geology
from .geology.regional.config import RegionalConfig, RegionalPolicy
from .geology.regional.service import initialize_regional_geology
from .environment.config import EnvironmentConfigC3
from .environment.service import initialize_environment
from .vegetation.config import VegetationConfigV2
from .vegetation import service as vegetation, resources, lifecycle
from .vegetation.growth_gameplay import LifeConfigGA1
from .vegetation.renewal_gameplay import initialize_ga2, RenewalConfigGA2
from .terrain.field import checksum
from .spatial import bind_location

PROFILE = 'world_genesis_ap1_v1'
PROFILE_WGS1 = 'world_genesis_ap1_tp1_wgs1_v1'
PROFILE_WGS1_V2 = 'world_genesis_ap1_tp1_wgs1_v2'
PROFILE_WGS2 = 'world_genesis_ap1_tp1_wgs2_v1'
PROFILE_WGS2_V2 = 'world_genesis_ap1_tp1_wgs2_v2'
PROFILE_WGS2_V3 = 'world_genesis_ap1_tp1_wgs2_v3'
PROFILE_WGS2_V4 = 'world_genesis_ap1_tp1_wgs2_v4'
PROFILE_WGS2_V5 = 'world_genesis_ap1_tp1_wgs2_v5'
PROFILE_WGS3_V1 = 'world_genesis_ap1_tp1_wgs3_v1'
FIELD_CAPABILITIES = {'precisao', 'corte_fino', 'ferramenta_apropriada_ao_tecido', 'manuseio_limpo'}
FIELD_MASTERY = 35
MAX_PROBES = 128
MAX_BODIES = 32


def bootstrap(db, campaign):
    if campaign.world_profile not in (PROFILE, PROFILE_WGS1, PROFILE_WGS1_V2, PROFILE_WGS2, PROFILE_WGS2_V2, PROFILE_WGS2_V3, PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1):
        raise ValueError('AP1 requires explicit campaign opt-in')
    started = perf_counter()
    cid = campaign.id
    initialize_world(db, cid, FormationConfigV4())
    initialize_terrain(db, cid, TerrainConfig())
    initialize_hydrology(db, cid, HydrologyConfig())
    initialize_regional_hydrology(db, cid, RegionalHydrologyConfig())
    initialize_climate(db, cid, ClimateConfigV3R1(land_recycling_ppm=550_000))
    # Empty, fixed evidence manifest: unresolved local passages stay blocked.
    initialize_water_balance(db, cid, WaterConfigC3R155(), regional_nodes=())
    initialize_geometry(db, cid, G1Config())
    initialize_reconciliation(db, cid, ReconciliationConfig(), cutover_minute=480)
    initialize_practical_hydrology(db, cid, PracticalConfig())
    initialize_geology(db, cid, GeologyConfig())
    initialize_regional_geology(db, cid, RegionalConfig(), RegionalPolicy())
    initialize_environment(db, cid, EnvironmentConfigC3())
    vegetation.initialize_vegetation(db, cid, VegetationConfigV2(
        policy=('regional_canopy_wgs2_canonical_v1' if campaign.world_profile in (PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1) else
                'regional_canopy_wgs2_microhabitat_v1' if campaign.world_profile == PROFILE_WGS2_V3 else 'regional_canopy_v2'),
        patch_spacing_m=1000), experimental=True)
    resources.initialize_resources(db, cid, resources.ResourceConfigR1(), experimental=True)
    lifecycle.initialize_life(db, cid, LifeConfigGA1(), experimental=True)
    initialize_ga2(db, cid, RenewalConfigGA2(), experimental=True)
    return perf_counter() - started


def find_start(db, campaign):
    """Seed-ordered macro probes, then actual eligible finite Vg2 founder slots."""
    v = vegetation.context(db, campaign.id)
    terrain = get_terrain_sampler(db, campaign.id)
    h = get_hydrology_plan(db, campaign.id)
    nodes = [i for i in range(len(h.heights)) if not h.drainage.marine[i] and h.heights[i] > h.sea_level_m]
    nodes.sort(key=lambda i: checksum([PROFILE, campaign.world_seed, 'spawn', i]))
    bodies = 0
    for attempt, node in enumerate(nodes[:MAX_PROBES], 1):
        point = cell_center(indexed_cell(node, h.config.level))
        if campaign.world_profile in (PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1):
            community_data = vegetation.sample_initial_community(db, campaign.id, v, point)
        else:
            community_data = v.sample(point)
        for pop in community_data['populations']:
            sp = v.catalog.species[pop['species_id']]
            parts = [p for p in sp.parts() if p['parte'] in ('folhas', 'fibras', 'frondes', 'ramos', 'talos', 'tufo')
                     and p['protocolo_campo_v7']['dificuldade_base_0_100'] <= FIELD_MASTERY
                     and set(p['protocolo_campo_v7']['capacidades_necessarias_da_ferramenta']) <= FIELD_CAPABILITIES
                     and any(k.endswith('principal_id') and val == 'EV-PROF-BOT-002'
                             for k, val in p['protocolo_campo_v7'].items())]
            if not parts or not pop['founder_count']:
                continue
            if bodies >= MAX_BODIES:
                raise ValueError(f'AP1: no accessible field site within {MAX_PROBES} probes/{MAX_BODIES} founder checks')
            bodies += 1
            try:
                row = vegetation.materialize_individual(db, campaign.id, point, sp.id, 0, _sampler=v)
            except ValueError as exc:
                if 'microsite unsupported' in str(exc):
                    continue
                raise
            q = SurfacePoint(*row.baseline['point'])
            t = terrain.sample(q)
            if t['height_mm'] <= terrain.plan.source.config.sea_level_m * 1000 or t['slope_proxy_ppm'] > 500_000:
                continue
            from app.game.time.clock import get_world_time
            clock = get_world_time(db, campaign.id)
            if any(row.state['part_stock'].get(p['id'], 0) > 0
                   and resources.available_now(db, campaign.id, v, row, p, clock)[0]
                   and lifecycle.phase_available(row.baseline, row.state, p['id'], clock.total_minutes(), sp) for p in parts):
                return q, attempt, bodies
    raise ValueError(f'AP1: no viable terrestrial vegetation site within {MAX_PROBES} probes; seed={campaign.world_seed}')


def provision_field_training(db, actor):
    """Finite opt-in expedition kit and basic collection training; no identification."""
    from app.game.items.service import create_item_definition, create_item_instance, move_item_instance, set_item_owner
    from app.game.items.tools import configure_item_tool_profile
    from app.game.items.equipment import configure_item_equipment_profile, equip_item
    definition = create_item_definition(db, key='ap1_field_scissors_v1', name='Tesoura de campo',
        item_type=ItemType.TOOL, instance_mode=ItemInstanceMode.UNIQUE, base_weight=0.2,
        description='Tesoura de precisão do equipamento experimental de campo; sem capacidades de escavação ou corte de árvores.')
    configure_item_tool_profile(db, definition, capabilities={ToolCapability.CUTTING})
    configure_item_equipment_profile(db, definition, allowed_slots={EquipmentSlot.WAIST, EquipmentSlot.OFF_HAND})
    vegetation.certify_botanical_tool(db, definition.id, FIELD_CAPABILITIES, experimental=True)
    tool = create_item_instance(db, definition)
    move_item_instance(db, tool, location_type=ItemLocationType.CHARACTER, location_ref=actor.id)
    set_item_owner(db, tool, owner_type=ItemOwnerType.CHARACTER, owner_ref=actor.id)
    # Field tools must be physically accessible to R1. A carried item defaults
    # to STOWED; placing the finite kit in the waist slot makes it QUICK without
    # occupying either hand needed by the legacy arrival equipment.
    equip_item(db, tool, slot=EquipmentSlot.WAIST)
    sid = 'EV-PROF-BOT-002'
    if db.get(Skill, sid) is None:
        db.add(Skill(id=sid, name='Coleta botânica', category='botanical'))
        db.flush()
    skill = db.query(CharacterSkill).filter_by(character_id=actor.id, skill_id=sid).first()
    if skill is None:
        db.add(CharacterSkill(character_id=actor.id, skill_id=sid, mastery=FIELD_MASTERY))
    return tool.id


def start_playable(db, campaign, actor, llm_service):
    from app.game.players.arrival_kit import grant_transported_arrival_kit
    from app.game.discovery.service import record_location_visit
    from app.game.game_state import build_game_state
    from app.api.serializers import to_game_state_response
    from app.schemas.campaign import WorldStartResponse
    t = perf_counter()
    if campaign.playable_state is None:
        preparation = bootstrap(db, campaign)
        q, probes, bodies = find_start(db, campaign)
        region = Region(campaign_id=campaign.id, name='Território de chegada',
                        description='Área geográfica experimental de exploração, sem atribuição política ou continental.')
        db.add(region); db.flush()
        location = Location(region_id=region.id, name='Clareira de chegada', type='genesis_field',
                            description='Vegetação local canônica. Este ponto de campo não é um assentamento gerado.')
        db.add(location); db.flush()
        bind_location(db, campaign.id, location.id, q)
        config = FormationConfigV4()
        materialize_sector(db, campaign.id, cell_at(q, config.sector_level))
        campaign.playable_state = {'profile': PROFILE, 'location_id': location.id, 'region_id': region.id,
            'vegetation_signature': vegetation.context(db, campaign.id).signature,
            'probes': probes, 'founder_checks': bodies, 'bootstrap_seconds': preparation,
            'initial_preparation_seconds': perf_counter()-t}
        if campaign.world_profile in (PROFILE_WGS1, PROFILE_WGS1_V2, PROFILE_WGS2, PROFILE_WGS2_V2, PROFILE_WGS2_V3, PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1):
            from .local_formations import (PROFILE as LOCAL_PROFILE, PROFILE_V2 as LOCAL_PROFILE_V2,
                SIGNAL_POLICY_V2, VERSION as WGS1_VERSION, VERSION_V2 as WGS1_VERSION_V2)
            is_wgs2 = campaign.world_profile in (PROFILE_WGS2, PROFILE_WGS2_V2, PROFILE_WGS2_V3, PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1)
            version = ('natural_formations_wgs2_v2' if campaign.world_profile in (PROFILE_WGS2_V2, PROFILE_WGS2_V3, PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1) else
                'natural_formations_wgs2_v1' if is_wgs2 else WGS1_VERSION_V2 if campaign.world_profile == PROFILE_WGS1_V2 else WGS1_VERSION)
            formation_policy = {'version': version,
                'selection_policy': 'wgs2-family-opportunities-r1' if is_wgs2 else LOCAL_PROFILE_V2 if campaign.world_profile == PROFILE_WGS1_V2 else LOCAL_PROFILE}
            if campaign.world_profile == PROFILE_WGS1_V2:
                formation_policy['signal_policy'] = SIGNAL_POLICY_V2
            campaign.playable_state = {**campaign.playable_state, 'natural_formations': formation_policy}
            if campaign.world_profile in (PROFILE_WGS2_V3, PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1):
                from .vegetation.microhabitat import VERSION as MICROHABITAT_VERSION, ORIGIN_LOOKUP_VERSION
                campaign.playable_state['microhabitats'] = {'version': MICROHABITAT_VERSION,
                    'origin_lookup_version': ORIGIN_LOOKUP_VERSION}
                if campaign.world_profile in (PROFILE_WGS2_V4, PROFILE_WGS2_V5, PROFILE_WGS3_V1):
                    from .vegetation.microhabitat_canonical import RESOLUTION_VERSION
                    campaign.playable_state['microhabitats']['canonical_resolution_version'] = RESOLUTION_VERSION
            if campaign.world_profile == PROFILE_WGS3_V1:
                from .local_water import VERSION as WATER_VERSION
                campaign.playable_state['local_water'] = {'version': WATER_VERSION,
                    'source_authority': 'genesis_local_water_bodies', 'collection_enabled': False}
        from .territory import initialize_territory
        initialize_territory(db, campaign, location)
    descriptor = campaign.playable_state
    if descriptor['profile'] != PROFILE or descriptor['vegetation_signature'] != vegetation.context(db, campaign.id).signature:
        raise ValueError('AP1 persisted descriptor/source mismatch; no automatic conversion')
    if campaign.world_profile == PROFILE_WGS3_V1:
        from .local_water import VERSION as WATER_VERSION
        if descriptor.get('local_water') != {'version': WATER_VERSION,
                'source_authority': 'genesis_local_water_bodies', 'collection_enabled': False}:
            raise ValueError('WGS3 local water contract mismatch; no automatic conversion')
    if actor.location_id is None:
        actor.region_id = descriptor['region_id']; actor.location_id = descriptor['location_id']
        record_location_visit(db, actor.id, actor.location_id, source='world_start')
        grant_transported_arrival_kit(db, actor)
        provision_field_training(db, actor)
        from .vegetation.actions import encounter
        plants = encounter(db, campaign.id, actor)
        facts = {'arrival': 'Chegada em terreno firme com vegetação real próxima.',
                 'preparation': 'Perfil experimental: equipamento de campo de precisão e instrução básica de coleta (35); identificação de espécies não concedida.',
                 'nearby': observable_facts({'individuals': plants})}
        narrative, unavailable = narrate_facts(db, campaign.id, actor.id, llm_service, facts, 'Início da exploração', opening=True)
        log_event(db, campaign.id, EventType.WORLD_STARTED, actor_type='character', actor_id=actor.id,
                  payload={'narrative': narrative, 'narrator_unavailable': unavailable, 'mechanical_summary': str(facts), 'arrival_kind': PROFILE})
    db.commit()
    state = build_game_state(db, campaign.id, actor.id)
    return WorldStartResponse(narrative=state.opening_narrative or 'A clareira permanece diante de você.',
        narrator_unavailable=state.opening_narrator_unavailable, state=to_game_state_response(db, state))


def observable_facts(result):
    """Whitelist public observations: never pass hidden species or stock coordinates to LLM."""
    if 'individuals' in result:
        return [observable_facts(p) for p in result['individuals']]
    keys = ('kind', 'height_cm', 'alive', 'maturity', 'identified', 'name', 'quantity', 'unit_mass_mg', 'exported_mass_mg', 'individual_alive')
    facts = {k: result[k] for k in keys if k in result}
    if 'parts' in result:
        facts['parts'] = [{k: p[k] for k in ('part', 'remaining', 'available_now', 'reason') if k in p} for p in result['parts']]
    return facts


def narrate_facts(db, cid, actor_id, llm, facts, text, *, opening=False):
    import json
    from app.ai import narrator, context_builder
    from app.ai.llm_service import LLMServiceError
    from app.game.game_state import build_game_state
    summary = json.dumps(facts, ensure_ascii=False)
    try:
        prose = narrator.narrate(llm, 'Fatos confirmados; não acrescente espécies, recursos, quantidades, locais ou descobertas: '+summary,
            context_builder.build_context(db, build_game_state(db, cid, actor_id)), player_input=text,
            recent_history='Exploração vegetal experimental; somente fatos confirmados.', mode='OPENING' if opening else 'ACTION')
        return prose, False
    except LLMServiceError:
        return ('Você chega a uma clareira com vegetação próxima. Recebe o equipamento de campo e instrução básica de coleta.'
                if opening else 'Você examina a vegetação próxima. Os detalhes observáveis estão listados abaixo.'), True
