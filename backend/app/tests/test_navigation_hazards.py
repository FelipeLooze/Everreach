"""Phase 17K — Natural Exploration Hazards."""

from app.core.enums import EventType, GeographicKnowledgeAspect, GeographicPrecision, KnowerType, NavigationRisk
from app.db.models.event import WorldEvent
from app.game.character.service import create_character
from app.game.exploration.hazards import assess_navigation_risk, resolve_navigation
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.knowledge.routes import grant_route_knowledge
from app.game.time.clock import get_world_time
from app.game.world.seed import create_campaign, seed_initial_region


class _FixedRoll:
    def __init__(self, raw: int):
        self.raw = raw

    def randint(self, a, b):
        return self.raw


def test_no_knowledge_at_all_is_high_risk(db_session):
    campaign = create_campaign(db_session, "Risco Alto", world_seed=1)
    logan = create_character(db_session, campaign.id, "Logan")

    risk = assess_navigation_risk(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_never_taught"
    )
    assert risk == NavigationRisk.HIGH


def test_vague_direction_alone_is_moderate_risk(db_session):
    campaign = create_campaign(db_session, "Risco Moderado", world_seed=2)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.DIRECTION, "Fica ao sul.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven",
        GeographicKnowledgeAspect.DIRECTION, precision=GeographicPrecision.VAGUE,
    )

    risk = assess_navigation_risk(db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven")
    assert risk == NavigationRisk.MODERATE


def test_known_route_with_good_direction_is_low_risk(db_session):
    campaign = create_campaign(db_session, "Risco Baixo", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)

    from app.db.models.location import LocationConnection

    connection = (
        db_session.query(LocationConnection)
        .filter(LocationConnection.from_location_id == village.id)
        .first()
    )
    grant_route_knowledge(db_session, campaign.id, KnowerType.PLAYER, logan.id, connection, source="exploração")
    ensure_geographic_fact(
        db_session, campaign.id, "location", connection.to_location_id, GeographicKnowledgeAspect.DIRECTION,
        "Fica logo ali perto.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "location", connection.to_location_id, GeographicKnowledgeAspect.DIRECTION,
        precision=GeographicPrecision.GOOD,
    )

    risk = assess_navigation_risk(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "location", connection.to_location_id
    )
    assert risk == NavigationRisk.LOW


def test_high_risk_navigation_can_get_a_character_lost(db_session):
    campaign = create_campaign(db_session, "Perdido", world_seed=4)
    logan = create_character(db_session, campaign.id, "Logan")

    before = get_world_time(db_session, campaign.id).total_minutes()
    risk, got_lost, extra = resolve_navigation(
        db_session, campaign.id, logan.id, "settlement", "loc_never_taught", rng=_FixedRoll(1)
    )
    after = get_world_time(db_session, campaign.id).total_minutes()

    assert risk == NavigationRisk.HIGH
    assert got_lost is True
    assert extra > 0
    assert after - before == extra

    event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.campaign_id == campaign.id, WorldEvent.event_type == EventType.NAVIGATION_HAZARD_ENCOUNTERED.value)
        .first()
    )
    assert event is not None


def test_low_risk_navigation_with_a_good_roll_never_gets_lost(db_session):
    campaign = create_campaign(db_session, "Nunca Perdido", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)

    from app.db.models.location import LocationConnection

    connection = (
        db_session.query(LocationConnection)
        .filter(LocationConnection.from_location_id == village.id)
        .first()
    )
    grant_route_knowledge(db_session, campaign.id, KnowerType.PLAYER, logan.id, connection, source="exploração")
    ensure_geographic_fact(
        db_session, campaign.id, "location", connection.to_location_id, GeographicKnowledgeAspect.DIRECTION,
        "Fica logo ali perto.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "location", connection.to_location_id, GeographicKnowledgeAspect.DIRECTION,
        precision=GeographicPrecision.PRECISE,
    )

    _risk, got_lost, extra = resolve_navigation(
        db_session, campaign.id, logan.id, "location", connection.to_location_id, rng=_FixedRoll(20)
    )

    assert got_lost is False
    assert extra == 0
