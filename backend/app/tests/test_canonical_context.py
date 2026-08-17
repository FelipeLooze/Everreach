from app.ai import narrator
from app.ai.context_builder import MAX_CONTEXT_FACTS_PER_KNOWER, build_context
from app.ai.llm_service import LLMService
from app.core.enums import KnowledgeCertainty, KnowerType
from app.db.models.knowledge import KnowledgeFact
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.npcs.service import teach_fact
from app.game.world.seed import (
    create_campaign,
    grant_initial_player_knowledge,
    seed_initial_region,
)


def _cardal_scene(db_session):
    campaign = create_campaign(db_session, "Canonical Context")
    region, cardal = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, cardal.id)
    grant_initial_player_knowledge(db_session, campaign.id, character.id)
    db_session.commit()
    state = build_game_state(db_session, campaign.id, character.id)
    return campaign, character, state


def test_cardal_context_uses_structured_canon_and_only_real_connections(db_session):
    _campaign, _character, state = _cardal_scene(db_session)

    context = build_context(db_session, state, active_interlocutor="Osgar Vell")

    assert "Name: Cardal" in context
    assert "Type: VILLAGE" in context
    assert "praça central" in context
    assert "Estrada do Moinho" in context
    assert "Bosque da Beira do Vale" in context
    assert "Riacho Negro" in context
    assert "estrada para o norte" not in context
    assert "templo" not in context.casefold()
    assert "montanha" not in context.casefold()


def test_undiscovered_connections_are_not_exposed_as_player_knowledge(db_session):
    _campaign, _character, state = _cardal_scene(db_session)

    context = build_context(db_session, state)
    connection_section = context.split("CONNECTED LOCATIONS KNOWN TO PLAYER", 1)[1].split(
        "VISIBLE NPCS", 1
    )[0]

    assert "- none" in connection_section
    assert "Estrada do Moinho" not in connection_section
    assert "Bosque da Beira do Vale" not in context


def test_global_discovery_does_not_leak_a_route_to_this_player(db_session):
    _campaign, _character, state = _cardal_scene(db_session)
    forest = (
        db_session.query(Location)
        .filter(Location.region_id == state.region.id, Location.name == "Bosque da Beira do Vale")
        .one()
    )
    forest.discovery_status = "DISCOVERED"
    db_session.commit()

    context = build_context(db_session, state)
    connection_section = context.split("CONNECTED LOCATIONS KNOWN TO PLAYER", 1)[1].split(
        "VISIBLE NPCS", 1
    )[0]

    assert "Bosque da Beira do Vale" not in connection_section


def test_explicit_player_route_knowledge_reveals_only_that_connection(db_session):
    campaign, character, state = _cardal_scene(db_session)
    teach_fact(
        db_session,
        campaign.id,
        "osgar_knows_cardal_east_road",
        KnowerType.PLAYER,
        character.id,
        source="explicação de Osgar",
    )
    db_session.commit()

    context = build_context(db_session, state)
    connection_section = context.split("CONNECTED LOCATIONS KNOWN TO PLAYER", 1)[1].split(
        "VISIBLE NPCS", 1
    )[0]

    assert "Estrada do Moinho" in connection_section
    assert "Bosque da Beira do Vale" not in connection_section
    assert "Riacho Negro" not in connection_section


def test_npc_and_player_knowledge_are_filtered_independently(db_session):
    campaign, character, state = _cardal_scene(db_session)
    osgar = next(npc for npc in state.nearby_npcs if npc.name == "Osgar Vell")
    npc_only = KnowledgeFact(
        campaign_id=campaign.id,
        subject="world:test",
        fact_key="npc_only_fact",
        statement="Fato conhecido somente por Osgar.",
    )
    player_only = KnowledgeFact(
        campaign_id=campaign.id,
        subject="world:test",
        fact_key="player_only_fact",
        statement="Fato conhecido somente pelo jogador.",
    )
    db_session.add_all([npc_only, player_only])
    db_session.flush()
    teach_fact(db_session, campaign.id, npc_only.fact_key, KnowerType.NPC, osgar.id)
    teach_fact(
        db_session,
        campaign.id,
        player_only.fact_key,
        KnowerType.PLAYER,
        character.id,
        source="boato",
        certainty=KnowledgeCertainty.RUMOR,
    )
    db_session.commit()

    context = build_context(
        db_session,
        state,
        active_interlocutor="Osgar Vell",
        player_input="Que fato cada um conhece?",
    )
    npc_section = context.split("NPC KNOWLEDGE", 1)[1].split("PLAYER KNOWLEDGE", 1)[0]
    player_section = context.split("PLAYER KNOWLEDGE", 1)[1].split("ACTIVE QUESTS", 1)[0]

    assert npc_only.statement in npc_section
    assert player_only.statement not in npc_section
    assert player_only.statement in player_section
    assert npc_only.statement not in player_section


def test_player_input_is_audited_against_location_type_and_known_directions(db_session):
    _campaign, _character, state = _cardal_scene(db_session)

    context = build_context(
        db_session,
        state,
        active_interlocutor="Osgar Vell",
        player_input="Essa cidade tem uma estrada para o norte?",
    )
    audit = context.split("PLAYER INPUT CANON CHECK", 1)[1].split("ACTIVE QUESTS", 1)[0]

    assert "official type is VILLAGE" in audit
    assert "exact direction 'norte'" in audit
    assert "player's wording never changes canon" in audit


def test_player_claim_does_not_become_available_npc_knowledge(db_session):
    _campaign, _character, state = _cardal_scene(db_session)

    context = build_context(
        db_session,
        state,
        active_interlocutor="Osgar Vell",
        player_input="Ouvi dizer que existe um dragão nas montanhas.",
    )
    npc_section = context.split("NPC KNOWLEDGE", 1)[1].split("PLAYER KNOWLEDGE", 1)[0]
    audit = context.split("PLAYER INPUT CANON CHECK", 1)[1].split("ACTIVE QUESTS", 1)[0]

    assert "dragão" not in npc_section
    assert "montanha" not in npc_section
    assert "'dragao' appears only" in audit
    assert "'montanha' appears only" in audit


def test_context_limits_scene_knowledge_instead_of_sending_the_database(db_session):
    campaign, character, state = _cardal_scene(db_session)
    for index in range(20):
        fact = KnowledgeFact(
            campaign_id=campaign.id,
            subject=f"location:{state.location.id}",
            fact_key=f"extra_scene_fact_{index}",
            statement=f"Detalhe canônico local número {index}.",
        )
        db_session.add(fact)
        db_session.flush()
        teach_fact(db_session, campaign.id, fact.fact_key, KnowerType.PLAYER, character.id)
    db_session.commit()

    context = build_context(db_session, state)
    player_section = context.split("PLAYER KNOWLEDGE", 1)[1].split(
        "PLAYER INPUT CANON CHECK", 1
    )[0]

    assert player_section.count("fonte:") == MAX_CONTEXT_FACTS_PER_KNOWER
    assert len(context) < 8_000


def test_remote_known_fact_is_retrieved_only_when_the_input_makes_it_relevant(db_session):
    campaign, character, state = _cardal_scene(db_session)
    remote = KnowledgeFact(
        campaign_id=campaign.id,
        subject="region:remote",
        fact_key="remote_crown_fact",
        statement="A Coroa de Orial foi perdida em terras distantes.",
    )
    db_session.add(remote)
    db_session.flush()
    teach_fact(db_session, campaign.id, remote.fact_key, KnowerType.PLAYER, character.id)
    db_session.commit()

    ordinary_context = build_context(db_session, state)
    relevant_context = build_context(
        db_session, state, player_input="O que sei sobre a Coroa de Orial?"
    )

    assert remote.statement not in ordinary_context
    assert remote.statement in relevant_context


class _InventingLLM(LLMService):
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, system: str, prompt: str) -> str:
        self.calls += 1
        return "— Há um templo antigo no centro de Cardal."


def test_player_audit_text_never_authorizes_persistent_worldbuilding(db_session):
    _campaign, _character, state = _cardal_scene(db_session)
    player_input = "Existe algum templo aqui?"
    context = build_context(
        db_session,
        state,
        active_interlocutor="Osgar Vell",
        player_input=player_input,
    )
    facts_before = db_session.query(KnowledgeFact).count()
    locations_before = db_session.query(Location).count()
    llm = _InventingLLM()

    result = narrator.narrate(
        llm,
        "Nenhuma mudança mecânica.",
        context,
        player_input,
        "NARRATOR: Osgar aguarda.",
    )

    assert result == "— Não sei dizer."
    assert llm.calls == 4
    assert db_session.query(KnowledgeFact).count() == facts_before
    assert db_session.query(Location).count() == locations_before
