"""Phase 15M — Player Knowledge Initialization.

WORLD EXISTS != PLAYER KNOWS THE WORLD. A massive, fully-generated Region
(dozens of subregions/settlements/organizations/POIs — Phases 15C-15L)
must not leak into what a freshly-arrived character actually knows. This
subphase found no code to change (audit): CharacterLocationDiscovery/
KnowledgeKnower are already strictly opt-in — nothing in seed_initial_region
creates one for the player, and known_map/context_builder already only
surface rows that exist. These tests lock that guarantee in as a
regression check now that the Region is actually massive.
"""

from app.core.enums import DiscoveryStatus, KnowerType
from app.db.models.knowledge import KnowledgeKnower
from app.db.models.location import CharacterLocationDiscovery
from app.db.models.npc import NPC
from app.db.models.organization import Organization
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.map.service import known_map
from app.game.world.seed import create_campaign, grant_initial_player_knowledge, seed_initial_region


def _start(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    grant_initial_player_knowledge(db_session, campaign.id, character.id)
    return campaign, region, village, character


def test_massive_region_generates_much_more_than_the_player_will_know(db_session):
    """Sanity check that this test is actually exercising a massive
    region, not a trivial one — otherwise the isolation tests below would
    pass vacuously."""
    campaign, region, village, character = _start(db_session)

    subregion_count = db_session.query(Subregion).filter(Subregion.region_id == region.id).count()
    settlement_count = db_session.query(Settlement).count()
    organization_count = db_session.query(Organization).filter(Organization.campaign_id == campaign.id).count()

    assert subregion_count >= 8
    assert settlement_count >= 7  # one major settlement per non-anchor subregion (min 8 - 1 anchor)
    assert organization_count >= 7


def test_known_map_only_shows_the_starting_village(db_session):
    campaign, region, village, character = _start(db_session)

    result = known_map(db_session, campaign.id, character.id)

    location_names = [loc["name"] if isinstance(loc, dict) else loc.name for loc in result["locations"]]
    assert location_names == ["Cardal"]


def test_player_learns_no_facts_beyond_the_initial_grant(db_session):
    campaign, region, village, character = _start(db_session)

    known_fact_ids = {
        row[0]
        for row in db_session.query(KnowledgeKnower.fact_id)
        .filter(
            KnowledgeKnower.knower_type == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id == character.id,
        )
        .all()
    }

    assert len(known_fact_ids) == 1


def test_player_has_no_discovery_rows_beyond_the_starting_village(db_session):
    campaign, region, village, character = _start(db_session)

    discoveries = (
        db_session.query(CharacterLocationDiscovery)
        .filter(CharacterLocationDiscovery.character_id == character.id)
        .all()
    )

    assert len(discoveries) == 1
    assert discoveries[0].location_id == village.id


def test_player_does_not_automatically_know_any_generated_npc_by_name(db_session):
    """The region's dozens of generated leader NPCs must remain
    undiscovered — only Cardal's own hand-authored NPCs are anywhere near
    the starting character, and even those require Knowledge, not name
    leakage through Region-scoped queries."""
    campaign, region, village, character = _start(db_session)

    npc_count = db_session.query(NPC).filter(NPC.campaign_id == campaign.id).count()
    assert npc_count > 3  # more than just Osgar/Mira/Talven exist in the world

    known_fact_ids = {
        row[0]
        for row in db_session.query(KnowledgeKnower.fact_id)
        .filter(
            KnowledgeKnower.knower_type == KnowerType.PLAYER.value,
            KnowledgeKnower.knower_id == character.id,
        )
        .all()
    }
    assert len(known_fact_ids) == 1
