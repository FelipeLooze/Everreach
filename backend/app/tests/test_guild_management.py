"""Phase 13 close-out: ranks, shared goals and relations between guilds."""
import random

from app.core.enums import (
    ActionIntentType,
    CombatActorType,
    EventType,
    GuildFocus,
    OrganizationGoalStatus,
    OrganizationOrigin,
    OrganizationRelationType,
    OrganizationVisibility,
    RiskTolerance,
)
from app.ai.intent_parser import Intent
from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.organization import Organization, OrganizationGoal
from app.db.models.simulated_player import SimulatedPlayer
from app.game import engine
from app.game.groups.companions import invite_simulated_player
from app.game.organizations import guild_goals, player_guilds
from app.game.organizations.relations import active_relations_between
from app.game.organizations.service import create_organization
from app.game.players import service as players_service
from app.game.relationships.service import record_simulated_players_interaction
from app.game.time import clock
from app.services.event_log import log_event
from app.simulation import society_simulation as society

DAY = 24 * 60


def _started_world(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Guild management"}).json()
    character_data = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    client.post(
        f"/api/campaigns/{campaign['id']}/start", params={"character_id": character_data["id"]}
    )
    character = db_session.get(Character, character_data["id"])
    transported = {
        player.risk_tolerance: player
        for player in db_session.query(SimulatedPlayer).filter(
            SimulatedPlayer.campaign_id == campaign["id"],
            SimulatedPlayer.location_id == character.location_id,
        )
    }
    return campaign["id"], character, transported


def _player_guild(db_session, campaign_id, character, *players, text='Fundamos uma guilda chamada "Forja"'):
    for player in players:
        players_service.meet_simulated_player(db_session, campaign_id, character.id, player.id)
        assert invite_simulated_player(db_session, campaign_id, character, player).changed
    assert player_guilds.found_guild(db_session, campaign_id, character, text).changed
    return player_guilds.transported_guild_of(db_session, CombatActorType.CHARACTER, character.id)


def _extra_transported(db_session, campaign_id, location_id, name):
    player = SimulatedPlayer(
        campaign_id=campaign_id, name=name, location_id=location_id,
        risk_tolerance=RiskTolerance.BALANCED,
    )
    db_session.add(player)
    db_session.flush()
    return player


def _simulated_guild(db_session, campaign_id, name, focus, leader, *founders):
    organization = create_organization(
        db_session, campaign_id, name,
        organization_type=player_guilds.FOCUS_TYPES[focus],
        origin=OrganizationOrigin.TRANSPORTED_CREATED,
        visibility=OrganizationVisibility.PRIVATE,
        founder_type=CombatActorType.SIMULATED_PLAYER, founder_id=leader.id,
    )
    player_guilds._staff_new_guild(
        db_session, campaign_id, organization, focus,
        leader=(CombatActorType.SIMULATED_PLAYER, leader.id),
        founders=[(CombatActorType.SIMULATED_PLAYER, founder.id) for founder in founders],
    )
    return organization


def _title(db_session, organization, actor_id):
    member = next(
        member for member in player_guilds._active_members(db_session, organization)
        if member.member_id == actor_id
    )
    return player_guilds._role(db_session, organization, player_guilds._rank_of(db_session, member)).title


# --- Ranks -----------------------------------------------------------------------


def test_the_leader_promotes_demotes_and_hands_over_the_guild(client, db_session):
    campaign_id, character, transported = _started_world(client, db_session)
    bram = transported[RiskTolerance.BOLD]
    guild = _player_guild(db_session, campaign_id, character, bram)

    promoted = player_guilds.promote(db_session, character, bram)
    assert promoted.changed and _title(db_session, guild, bram.id) == "Oficial"
    assert not player_guilds.promote(db_session, character, bram).changed

    assert player_guilds.demote(db_session, character, bram).changed
    assert _title(db_session, guild, bram.id) == "Membro"

    handed = player_guilds.transfer_leadership(db_session, character, bram)
    assert handed.changed
    assert _title(db_session, guild, bram.id) == "Mestre da Guilda"
    assert _title(db_session, guild, character.id) == "Oficial"

    refused = player_guilds.promote(db_session, character, bram)
    assert not refused.changed and "Só o líder" in refused.summary


def test_rank_and_diplomacy_backstops():
    def refined(text):
        intent = Intent(type=ActionIntentType.FREEFORM, target=None, raw_text=text)
        return engine._refine_explicit_membership_intent(intent).type

    assert refined("Promovo o Bram a oficial da guilda") == ActionIntentType.CHANGE_GUILD_RANK
    assert refined("Passo a liderança para a Dessa") == ActionIntentType.CHANGE_GUILD_RANK
    assert refined("Proponho uma aliança entre nossas guildas") == ActionIntentType.GUILD_DIPLOMACY
    assert refined("Declaro os Lobos Cinzentos nossos rivais") == ActionIntentType.GUILD_DIPLOMACY
    assert refined("Rompo a aliança com eles") == ActionIntentType.GUILD_DIPLOMACY
    assert refined("Vamos viajar juntos") == ActionIntentType.INVITE_TO_GROUP


# --- Shared goals ----------------------------------------------------------------


def test_a_new_guild_gets_its_focus_goal_and_counts_real_trips(client, db_session, monkeypatch):
    campaign_id, character, transported = _started_world(client, db_session)
    bram = transported[RiskTolerance.BOLD]
    guild = _player_guild(
        db_session, campaign_id, character, bram,
        text='Fundamos uma guilda de caçadores chamada "Lobos Cinzentos"',
    )
    goal = guild_goals.current_goal(db_session, guild)
    assert (goal.metric, goal.target) == (guild_goals.MEMBERS, 4)
    assert guild_goals.update_goal(db_session, guild) is None and goal.progress == 2

    monkeypatch.setitem(
        guild_goals._LADDERS, GuildFocus.HUNTERS,
        ((guild_goals.MEMBERS, 2), (guild_goals.WILD_TRIPS, 2), (guild_goals.MEMBERS, 6)),
    )
    goal.target = 2
    assert guild_goals.update_goal(db_session, guild) is goal
    goal = guild_goals.current_goal(db_session, guild)
    assert (goal.metric, goal.target) == (guild_goals.WILD_TRIPS, 2)
    forest = Location(region_id=db_session.get(Location, character.location_id).region_id,
                      name="Mata Funda", type="forest")
    db_session.add(forest)
    db_session.flush()

    def arrive(actor_type, actor_id, event_type):
        log_event(db_session, campaign_id, event_type, actor_type=actor_type, actor_id=actor_id,
                  payload={"to_location_id": forest.id})

    # Logan and Bram arriving together are one trip, not two.
    arrive("character", character.id, EventType.PLAYER_MOVED)
    arrive("simulated_player", bram.id, EventType.SIMULATED_PLAYER_MOVED)
    assert guild_goals.update_goal(db_session, guild) is None
    assert goal.progress == 1

    clock.advance_world_time(db_session, campaign_id, 3 * 60)
    arrive("simulated_player", bram.id, EventType.SIMULATED_PLAYER_MOVED)
    achieved = guild_goals.update_goal(db_session, guild)

    assert achieved is goal and goal.status == OrganizationGoalStatus.ACHIEVED
    following = guild_goals.current_goal(db_session, guild)
    assert (following.metric, following.target) == (guild_goals.MEMBERS, 6)
    assert guild_goals.achieved_count(db_session, guild) == 2

    social = client.get(
        f"/api/campaigns/{campaign_id}/social", params={"character_id": character.id}
    ).json()
    (summary,) = [org for org in social["organizations"] if org["name"] == "Lobos Cinzentos"]
    assert summary["goal"] == {"description": following.description, "progress": 0, "target": 6}
    assert summary["goals_achieved"] == 2
    assert summary["focus"] == GuildFocus.HUNTERS


# --- Relations -------------------------------------------------------------------


def test_player_diplomacy_needs_the_other_leader_and_rivalry_ends_alliances(client, db_session):
    campaign_id, character, transported = _started_world(client, db_session)
    bram, corren = transported[RiskTolerance.BOLD], transported[RiskTolerance.BALANCED]
    dessa = _extra_transported(db_session, campaign_id, character.location_id, "Dessa Vorn")
    theirs = _simulated_guild(db_session, campaign_id, "Arcos do Norte", GuildFocus.HUNTERS, bram, dessa)
    ours = _player_guild(db_session, campaign_id, character, corren)

    stranger = player_guilds.propose_alliance(db_session, campaign_id, character, theirs, bram)
    assert not stranger.changed and "não conhece" in stranger.summary

    players_service.meet_simulated_player(db_session, campaign_id, character.id, bram.id)
    allied = player_guilds.propose_alliance(db_session, campaign_id, character, theirs, bram)
    assert allied.changed
    assert [relation.relation_type for relation in active_relations_between(db_session, ours.id, theirs.id)] == [
        OrganizationRelationType.ALLIED
    ]

    assert player_guilds.declare_rivalry(db_session, character, theirs).changed
    assert [relation.relation_type for relation in active_relations_between(db_session, ours.id, theirs.id)] == [
        OrganizationRelationType.RIVAL
    ]
    assert not player_guilds.break_alliance(db_session, character, theirs).changed
    rebuffed = player_guilds.propose_alliance(db_session, campaign_id, character, theirs, bram)
    assert not rebuffed.changed and "rival" in rebuffed.summary


def test_relations_emerge_between_simulated_guilds(client, db_session, monkeypatch):
    campaign_id, character, transported = _started_world(client, db_session)
    here = character.location_id
    people = [_extra_transported(db_session, campaign_id, here, f"Pessoa {index}") for index in range(10)]
    hunters_a = _simulated_guild(db_session, campaign_id, "Arcos do Norte", GuildFocus.HUNTERS, people[0], people[1])
    hunters_b = _simulated_guild(db_session, campaign_id, "Presas de Prata", GuildFocus.HUNTERS, people[2], people[3])
    bandits = _simulated_guild(db_session, campaign_id, "Mãos Sujas", GuildFocus.BANDITS, people[4], people[5])
    merchants = _simulated_guild(db_session, campaign_id, "Rota do Sal", GuildFocus.MERCHANTS, people[6], people[7])
    hunters_c = _simulated_guild(db_session, campaign_id, "Falcões do Ermo", GuildFocus.HUNTERS, people[8], people[9])
    record_simulated_players_interaction(db_session, campaign_id, people[0].id, people[6].id, affinity_delta=1)
    for name in ("RIVALRY_CHANCE", "HOSTILITY_CHANCE", "ALLIANCE_CHANCE"):
        monkeypatch.setattr(society, name, 1.0)

    formed = society._settle_relations(db_session, campaign_id, random.Random(1))

    def types(first, second):
        return {relation.relation_type for relation in active_relations_between(db_session, first.id, second.id)}

    hunters = (hunters_a, hunters_b, hunters_c)
    hunter_pairs = [(first, second) for index, first in enumerate(hunters) for second in hunters[index + 1:]]
    # Caps: one emergent rival per guild, two guilds hunting one crew.
    assert [types(*pair) for pair in hunter_pairs].count({OrganizationRelationType.RIVAL}) == 1
    assert [types(guild, bandits) for guild in hunters].count({OrganizationRelationType.HOSTILE}) == 2
    assert types(hunters_a, merchants) == {OrganizationRelationType.ALLIED}
    assert types(bandits, merchants) == set()
    assert formed == 4
    # A settled pair is left alone the next week.
    assert society._settle_relations(db_session, campaign_id, random.Random(1)) == 0


def test_promotion_through_the_engine_even_when_the_parser_reads_conversation(client, db_session):
    import json

    from app.ai.llm_service import LLMService

    class Parser(LLMService):
        def generate(self, system, prompt):
            if "Ação do jogador" in prompt:
                return json.dumps({"intent": "FREEFORM", "target": None})
            return "Logan anuncia a decisão à guilda."

    campaign_id, character, transported = _started_world(client, db_session)
    bram = transported[RiskTolerance.BOLD]
    guild = _player_guild(db_session, campaign_id, character, bram)
    db_session.commit()

    llm = Parser()
    engine.resolve_action(db_session, llm, campaign_id, character.id,
                          f"Promovo o {bram.name.split()[0]} a oficial da guilda", intent_llm_service=llm)

    assert _title(db_session, guild, bram.id) == "Oficial"
