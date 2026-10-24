"""The user's playtest of 2026-10-24 (save "Tteste"): XP spoken by the
guildmaster, a contract name pasted after a goodbye, "vocês foram quatro"
for the massive First Arrival, and walks that moved nobody."""

from app.core.enums import ActionIntentType, DiscoveryStatus
from app.db.models.location import CharacterLocationDiscovery, Location
from app.game import engine
from app.game.character.service import create_character
from app.game.economy.initial_content import ensure_initial_economy_for_campaign
from app.game.game_state import build_game_state
from app.ai.intent_parser import Intent
from app.game.world.seed import create_campaign, seed_initial_region


def _world(db_session):
    campaign = create_campaign(db_session, "Tteste")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    assert ensure_initial_economy_for_campaign(db_session, campaign.id)
    db_session.flush()
    return campaign, character, village


def _discover_all(db_session, character):
    for location in db_session.query(Location).filter(Location.region_id == character.region_id):
        row = db_session.query(CharacterLocationDiscovery).filter_by(
            character_id=character.id, location_id=location.id
        ).first()
        if row is None:
            db_session.add(CharacterLocationDiscovery(
                character_id=character.id, location_id=location.id, status=DiscoveryStatus.DISCOVERED.value,
            ))
        elif row.status == DiscoveryStatus.UNKNOWN.value:
            row.status = DiscoveryStatus.DISCOVERED.value
    db_session.flush()


def test_the_narrator_never_hears_xp():
    summary = (
        "Logan entrega o relato. Missão concluída. "
        "Recompensa de missão: Relato da Primeira Chegada: +10 XP base."
    )
    told = engine._without_progression_numbers(summary)

    assert "XP" not in told and "10" not in told
    assert told.endswith("Missão concluída: Relato da Primeira Chegada.")
    assert engine._without_progression_numbers("Logan trabalha (+4 XP base em Ferreiro).") == "Logan trabalha."


def test_the_first_arrival_is_described_as_massive(db_session):
    from app.ai.context_builder import _arrival_history_lines

    campaign, character, _village = _world(db_session)
    engine_state = build_game_state(db_session, campaign.id, character.id)
    from app.core.enums import EventType
    from app.db.models.event import WorldEvent

    if not db_session.query(WorldEvent).filter_by(
        campaign_id=campaign.id, event_type=EventType.WORLD_STARTED.value
    ).first():
        db_session.add(WorldEvent(
            campaign_id=campaign.id, event_type=EventType.WORLD_STARTED.value,
            world_minute=engine_state.world_time.total_minutes(),
        ))
        db_session.flush()

    line = " ".join(_arrival_history_lines(db_session, engine_state))
    assert "massive" in line and "never say only a handful arrived" in line


def test_taking_a_look_at_the_guild_walks_there(db_session):
    campaign, character, _village = _world(db_session)
    _discover_all(db_session, character)

    target = engine._resolve_movement_target(db_session, character, "Vou dar uma olhada na guilda")
    assert target is not None and target.type == "adventurers_guild"
    merchants = engine._resolve_movement_target(db_session, character, "Vou passar na guilda de comerciantes")
    assert merchants is not None and merchants.type == "merchants_guild"


def test_a_walk_without_a_destination_asks_where_instead_of_narrating(db_session):
    campaign, character, village = _world(db_session)
    _discover_all(db_session, character)
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.MOVE, target=None, raw_text="Vou na direção que ele indicou")
    summary, minutes = engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert minutes == 0 and character.location_id == village.id
    assert summary.startswith(engine.WHERE_TO_QUESTION) and "Lugares que você conhece:" in summary
    assert village.name not in summary.split("conhece:")[1].split(", ")


def test_a_building_next_to_the_square_can_be_walked_to_before_it_is_known(db_session):
    campaign, character, village = _world(db_session)
    state = build_game_state(db_session, campaign.id, character.id)

    intent = Intent(type=ActionIntentType.EXAMINE, target="guilda", raw_text='"Obrigado. Vou dar uma olhada na guilda"')
    engine._apply_intent(db_session, campaign.id, character, intent, state)

    assert db_session.get(Location, character.location_id).type == "adventurers_guild"


def test_the_narrator_knows_the_guildmasters_name(db_session):
    from app.ai.context_builder import _organization_leader_title
    from app.db.models.npc import NPC
    from app.db.models.organization import Organization

    campaign, _character, _village = _world(db_session)
    guild = db_session.query(Organization).filter(
        Organization.campaign_id == campaign.id, Organization.name.like("Guilda de Aventureiros%")
    ).first()
    master = db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id, NPC.role == "mestre da guilda de aventureiros"
    ).one()

    assert _organization_leader_title(db_session, guild.id).endswith(f", {master.name}")
