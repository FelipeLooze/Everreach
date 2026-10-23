"""Guilds founded by simulated transported people, slowly, over months."""
import json
import random

from app.ai.context_builder import fact_is_revealed_in_text
from app.ai.llm_service import LLMService
from app.core.enums import (
    CombatActorType,
    GuildFocus,
    KnowerType,
    OrganizationFormality,
    OrganizationOrigin,
    OrganizationVisibility,
    RiskTolerance,
    SimulatedPlayerArchetype,
)
from app.db.models.character import Character
from app.db.models.npc import NPC
from app.db.models.organization import Organization
from app.db.models.simulated_player import SimulatedPlayer, SimulatedPlayerPopulation
from app.game import engine
from app.game.npcs.service import KnownFact, knows
from app.game.organizations import player_guilds
from app.game.organizations.registration import register_with_organization
from app.game.players import service as players_service
from app.game.players.groups import create_group
from app.game.relationships.service import record_simulated_players_interaction
from app.game.time import clock
from app.simulation import society_simulation as society

DAY = 24 * 60


def _started_world(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Society"}).json()
    character_data = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    client.post(
        f"/api/campaigns/{campaign['id']}/start", params={"character_id": character_data["id"]}
    )
    character = db_session.get(Character, character_data["id"])
    transported = sorted(
        db_session.query(SimulatedPlayer).filter(SimulatedPlayer.campaign_id == campaign["id"]),
        key=lambda player: player.name,
    )
    return campaign["id"], character, transported


def _advance_to_day(db_session, campaign_id, day):
    now = clock.get_world_time(db_session, campaign_id).total_minutes()
    target = day * DAY
    if target > now:
        clock.advance_world_time(db_session, campaign_id, target - now)


def _week_tick(db_session, campaign_id):
    clock.advance_world_time(db_session, campaign_id, 7 * DAY)
    return society.tick(db_session, campaign_id, 7 * DAY, rng=random.Random(1))


def _old_group(db_session, campaign_id, leader, members, days_old=20):
    minute = clock.get_world_time(db_session, campaign_id).total_minutes() - days_old * DAY
    return create_group(db_session, campaign_id, leader, members, goal="Sobreviver juntos.",
                        occurred_world_minute=minute)


def _guilds(db_session, campaign_id):
    return db_session.query(Organization).filter(
        Organization.campaign_id == campaign_id,
        Organization.origin == OrganizationOrigin.TRANSPORTED_CREATED,
    ).all()


def test_one_person_a_week_steps_out_of_the_arrivals_up_to_the_cap(client, db_session, monkeypatch):
    campaign_id, character, transported = _started_world(client, db_session)
    db_session.add(SimulatedPlayerPopulation(location_id=character.location_id, abstract_count=60))
    db_session.flush()
    monkeypatch.setattr(society, "PERSISTENT_TRANSPORTED_CAP", len(transported) + 2)

    assert society.tick(db_session, campaign_id, 60, rng=random.Random(2)).materialized == 0
    results = [_week_tick(db_session, campaign_id).materialized for _ in range(3)]

    assert results == [1, 1, 0]
    people = db_session.query(SimulatedPlayer).filter(SimulatedPlayer.campaign_id == campaign_id).all()
    assert len(people) == len(transported) + 2
    assert len({person.name for person in people}) == len(people)


def test_no_guild_before_months_then_a_group_founds_one(client, db_session, monkeypatch):
    campaign_id, _character, (bram, corren, dessa) = _started_world(client, db_session)
    monkeypatch.setattr(society, "FOUND_CHANCE", 1.0)
    monkeypatch.setattr(society, "BANDIT_CHANCE", 0.0)
    corren.archetype = SimulatedPlayerArchetype.TRAINER
    _advance_to_day(db_session, campaign_id, 30)
    _old_group(db_session, campaign_id, corren, [bram])

    assert _week_tick(db_session, campaign_id).guilds_founded == 0

    _advance_to_day(db_session, campaign_id, society.GUILD_EMERGENCE_MIN_DAYS)
    assert _week_tick(db_session, campaign_id).guilds_founded == 1
    (guild,) = _guilds(db_session, campaign_id)
    assert guild.focus == GuildFocus.HUNTERS
    assert guild.formality == OrganizationFormality.INFORMAL
    assert knows(db_session, KnowerType.SIMULATED_PLAYER, bram.id,
                 player_guilds.guild_fact_key(guild), campaign_id)


def test_bold_crews_turn_to_banditry_without_the_cautious(client, db_session, monkeypatch):
    campaign_id, _character, (bram, corren, dessa) = _started_world(client, db_session)
    monkeypatch.setattr(society, "FOUND_CHANCE", 1.0)
    monkeypatch.setattr(society, "BANDIT_CHANCE", 1.0)
    bram.risk_tolerance = corren.risk_tolerance = RiskTolerance.BOLD
    dessa.risk_tolerance = RiskTolerance.CAUTIOUS
    _advance_to_day(db_session, campaign_id, society.GUILD_EMERGENCE_MIN_DAYS)
    _old_group(db_session, campaign_id, bram, [corren, dessa])

    _week_tick(db_session, campaign_id)

    (crew,) = _guilds(db_session, campaign_id)
    assert crew.focus == GuildFocus.BANDITS
    assert crew.visibility == OrganizationVisibility.SECRET
    assert player_guilds.transported_guild_of(db_session, CombatActorType.SIMULATED_PLAYER, dessa.id) is None


def test_guilds_recruit_acquaintances_and_seasoned_ones_register(client, db_session, monkeypatch):
    campaign_id, _character, (bram, corren, dessa) = _started_world(client, db_session)
    monkeypatch.setattr(society, "FOUND_CHANCE", 1.0)
    monkeypatch.setattr(society, "BANDIT_CHANCE", 0.0)
    dessa.risk_tolerance = RiskTolerance.BALANCED
    _advance_to_day(db_session, campaign_id, society.GUILD_EMERGENCE_MIN_DAYS)
    _old_group(db_session, campaign_id, bram, [corren])
    _week_tick(db_session, campaign_id)
    (guild,) = _guilds(db_session, campaign_id)

    record_simulated_players_interaction(db_session, campaign_id, corren.id, dessa.id)
    _week_tick(db_session, campaign_id)
    assert player_guilds.transported_guild_of(
        db_session, CombatActorType.SIMULATED_PLAYER, dessa.id
    ) == guild

    monkeypatch.setattr(society, "FORMALIZE_CHANCE", 1.0)
    for _ in range(5):
        _week_tick(db_session, campaign_id)

    assert guild.formality == OrganizationFormality.FORMALLY_RECOGNIZED
    assert guild.visibility == OrganizationVisibility.PUBLIC
    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").one()
    assert knows(db_session, KnowerType.NPC, elder.id, player_guilds.guild_fact_key(guild), campaign_id)


def _talk_parser(target_name):
    class Parser(LLMService):
        def generate(self, system, prompt):
            if "Ação do jogador" in prompt:
                return json.dumps({"intent": "TALK", "target": target_name})
            return "A conversa segue."

    return Parser()


def _found_with_leader(db_session, campaign_id, leader, member, monkeypatch, *, bandits=False):
    monkeypatch.setattr(society, "FOUND_CHANCE", 1.0)
    monkeypatch.setattr(society, "BANDIT_CHANCE", 1.0 if bandits else 0.0)
    if bandits:
        leader.risk_tolerance = member.risk_tolerance = RiskTolerance.BOLD
    _advance_to_day(db_session, campaign_id, society.GUILD_EMERGENCE_MIN_DAYS)
    _old_group(db_session, campaign_id, leader, [member])
    _week_tick(db_session, campaign_id)
    (guild,) = _guilds(db_session, campaign_id)
    return guild


def test_talking_with_a_member_reveals_the_guild_but_not_a_bandit_crew(client, db_session, monkeypatch):
    campaign_id, character, (bram, corren, _dessa) = _started_world(client, db_session)
    guild = _found_with_leader(db_session, campaign_id, bram, corren, monkeypatch)
    db_session.commit()

    llm = _talk_parser(bram.name)
    engine.resolve_action(db_session, llm, campaign_id, character.id, f"Falo com {bram.name}",
                          intent_llm_service=llm)

    assert knows(db_session, KnowerType.PLAYER, character.id, player_guilds.guild_fact_key(guild), campaign_id)
    social = client.get(
        f"/api/campaigns/{campaign_id}/social", params={"character_id": character.id}
    ).json()
    assert any(org["name"] == guild.name for org in social["organizations"])


def test_bandit_members_keep_their_crew_secret(client, db_session, monkeypatch):
    campaign_id, character, (bram, corren, _dessa) = _started_world(client, db_session)
    crew = _found_with_leader(db_session, campaign_id, bram, corren, monkeypatch, bandits=True)
    db_session.commit()

    llm = _talk_parser(bram.name)
    engine.resolve_action(db_session, llm, campaign_id, character.id, f"Falo com {bram.name}",
                          intent_llm_service=llm)

    assert not knows(db_session, KnowerType.PLAYER, character.id, player_guilds.guild_fact_key(crew), campaign_id)


def test_the_player_asks_a_guild_leader_to_join(client, db_session, monkeypatch):
    campaign_id, character, (bram, corren, _dessa) = _started_world(client, db_session)
    guild = _found_with_leader(db_session, campaign_id, bram, corren, monkeypatch)
    bram.location_id = character.location_id

    stranger = register_with_organization(db_session, campaign_id, character, "Posso entrar na sua guilda?")
    assert not stranger.changed and "não conhece" in stranger.summary

    players_service.meet_simulated_player(db_session, campaign_id, character.id, bram.id)
    accepted = register_with_organization(db_session, campaign_id, character, "Posso entrar na sua guilda?")

    assert accepted.changed
    assert player_guilds.transported_guild_of(db_session, CombatActorType.CHARACTER, character.id) == guild


def test_naming_a_guild_reveals_it():
    fact = KnownFact(
        subject="organization:org_1", fact_key="organization:org_1:exists",
        statement='Existe a guilda "Caçadores do Véu", fundada por Transportados e registrada no Conselho de Ravhelm.',
        source="", certainty="", discovered_at=None,
    )

    assert fact_is_revealed_in_text(fact, "— Os Caçadores do Véu pagam bem por peles.")
    assert not fact_is_revealed_in_text(fact, "— Há gente nova organizando caçadas por aí.")
