from app.ai.context_builder import active_npc_relevant_facts
from app.ai.intent_parser import Intent
from app.core.enums import ActionIntentType, DiscoveryStatus, KnowerType
from app.db.models.knowledge import KnowledgeFact
from app.db.models.location import CharacterLocationDiscovery, Location
from app.db.models.npc import NPC
from app.game import engine
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.npcs.service import knows, teach_fact
from app.game.world.local_knowledge import ensure_settlement_public_knowledge
from app.game.world.seed import create_campaign, grant_initial_player_knowledge, seed_initial_region
from app.simulation import npc_simulation


def _setup(db_session):
    campaign = create_campaign(db_session, "Local Knowledge")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    grant_initial_player_knowledge(db_session, campaign.id, character.id)
    ensure_settlement_public_knowledge(db_session, campaign.id, village.id)
    npc_simulation.tick(db_session, campaign.id, minutes=1)
    db_session.flush()
    return campaign, region, village, character


def test_local_elder_knows_real_service_route_and_worker(db_session):
    campaign, _region, village, _character = _setup(db_session)
    elder = (
        db_session.query(NPC)
        .filter(NPC.campaign_id == campaign.id, NPC.role == "ancião da vila")
        .one()
    )
    blacksmith = (
        db_session.query(NPC)
        .filter(NPC.campaign_id == campaign.id, NPC.role == "ferreira")
        .one()
    )
    forge = db_session.get(Location, blacksmith.workplace_location_id)
    facts = (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.campaign_id == campaign.id,
            KnowledgeFact.fact_key.in_(
                (
                    f"public_service_worker:{blacksmith.id}",
                )
            ),
        )
        .all()
    )

    assert forge.parent_location_id == village.id
    assert len(facts) == 1
    assert blacksmith.name in facts[0].statement
    assert forge.name in facts[0].statement
    assert knows(
        db_session,
        KnowerType.NPC,
        elder.id,
        facts[0].fact_key,
        campaign.id,
    )


def test_service_reveal_discovers_destination_and_movement_updates_visible_people(db_session):
    from app.game.discovery.service import record_location_visit

    campaign, _region, village, character = _setup(db_session)
    record_location_visit(db_session, character.id, village.id, source="arrival")
    elder = (
        db_session.query(NPC)
        .filter(NPC.campaign_id == campaign.id, NPC.role == "ancião da vila")
        .one()
    )
    blacksmith = (
        db_session.query(NPC)
        .filter(NPC.campaign_id == campaign.id, NPC.role == "ferreira")
        .one()
    )
    forge = db_session.get(Location, blacksmith.workplace_location_id)
    route_fact = (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.campaign_id == campaign.id,
            KnowledgeFact.fact_key.like("public_service_route:%"),
            KnowledgeFact.statement.contains(forge.name),
        )
        .one()
    )

    teach_fact(
        db_session,
        campaign.id,
        route_fact.fact_key,
        KnowerType.PLAYER,
        character.id,
        source=f"revelado por {elder.name}",
    )
    discovery = (
        db_session.query(CharacterLocationDiscovery)
        .filter(
            CharacterLocationDiscovery.character_id == character.id,
            CharacterLocationDiscovery.location_id == forge.id,
        )
        .one()
    )
    assert discovery.status == DiscoveryStatus.DISCOVERED.value

    summary, _minutes = engine._handle_move(
        db_session,
        campaign.id,
        character,
        Intent(
            type=ActionIntentType.MOVE,
            target="ferraria",
            raw_text="Ir até a ferraria.",
        ),
    )
    state = build_game_state(db_session, campaign.id, character.id)

    assert forge.name in summary
    assert character.location_id == forge.id
    assert blacksmith.id in {npc.id for npc in state.nearby_npcs}
    assert elder.id not in {npc.id for npc in state.nearby_npcs}

    # Playtest: the route back was never known, so the player was stuck
    # inside the forge ("Volto para a praça" was refused).
    summary, _minutes = engine._handle_move(
        db_session,
        campaign.id,
        character,
        Intent(
            type=ActionIntentType.MOVE,
            target="praça",
            raw_text="Volto para a praça.",
        ),
    )
    state = build_game_state(db_session, campaign.id, character.id)

    assert character.location_id == village.id, summary
    assert elder.id in {npc.id for npc in state.nearby_npcs}
    assert blacksmith.id not in {npc.id for npc in state.nearby_npcs}


def test_current_place_question_prioritizes_village_and_region_facts(db_session):
    campaign, region, _village, character = _setup(db_session)
    elder = (
        db_session.query(NPC)
        .filter(NPC.campaign_id == campaign.id, NPC.role == "ancião da vila")
        .one()
    )
    state = build_game_state(db_session, campaign.id, character.id)

    facts = active_npc_relevant_facts(
        db_session,
        state,
        elder.id,
        player_input="Onde estou? Qual é o nome desta região?",
    )

    keys = {fact.fact_key for fact in facts}
    assert "settlement_name_known" in keys
    assert "settlement_region_known" in keys
    assert any(region.name in fact.statement for fact in facts)



def test_naming_village_and_region_reveals_no_route_or_worker_fact(db_session):
    # Live playtest: the elder answered only "Ulhaven ... Vale das Águas
    # Claras", yet the inn, forge and east road were all taught as revealed.
    # The checker skips each statement's sentence-initial word, and the
    # templates opened with the very entity being taught ("Estalagem de X
    # fica...", "Trilha do Vale sai de X..."), leaving only the village and
    # region names to match.
    from app.ai.context_builder import fact_is_revealed_in_text
    from app.game.npcs.service import KnownFact

    campaign, region, village, _character = _setup(db_session)
    narration = (
        f"— {village.name}. A vila chama-se {village.name}. E a região... {region.name}."
    )
    facts = db_session.query(KnowledgeFact).filter(KnowledgeFact.campaign_id == campaign.id).all()

    revealed = {
        fact.fact_key
        for fact in facts
        if fact_is_revealed_in_text(
            KnownFact(
                subject=fact.subject,
                fact_key=fact.fact_key,
                statement=fact.statement,
                source="",
                certainty="",
                discovered_at=None,
            ),
            narration,
        )
    }

    assert revealed == {"settlement_name_known", "settlement_region_known"}
