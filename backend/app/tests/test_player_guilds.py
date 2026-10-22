"""Guilds founded by transported people, played from the protagonist's side."""
import json

from app.ai.llm_service import LLMService
from app.core.enums import (
    CombatActorType,
    GroupStatus,
    GuildFocus,
    KnowerType,
    OrganizationFormality,
    OrganizationMembershipStatus,
    OrganizationOrigin,
    OrganizationStatus,
    OrganizationType,
    OrganizationVisibility,
    RiskTolerance,
)
from app.db.models.character import Character
from app.db.models.group import Group
from app.db.models.npc import NPC
from app.db.models.organization import Organization, OrganizationMember, OrganizationRole
from app.db.models.simulated_player import SimulatedPlayer
from app.game import engine
from app.game.groups.companions import character_group, invite_simulated_player
from app.game.npcs.service import knows
from app.game.organizations import player_guilds
from app.game.organizations.registration import leave_organization
from app.game.organizations.reputation import award_organization_reputation
from app.game.players import service as players_service


def _started_world(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Player guilds"}).json()
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
    return campaign, character, transported


def _travel_with(db_session, campaign, character, *players):
    for player in players:
        players_service.meet_simulated_player(db_session, campaign["id"], character.id, player.id)
        assert invite_simulated_player(db_session, campaign["id"], character, player).changed


def _guild(db_session):
    return db_session.query(Organization).filter(
        Organization.origin == OrganizationOrigin.TRANSPORTED_CREATED
    ).one()


def _role_of(db_session, organization, actor_id):
    member = db_session.query(OrganizationMember).filter(
        OrganizationMember.organization_id == organization.id,
        OrganizationMember.member_id == actor_id,
        OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
    ).one_or_none()
    return db_session.get(OrganizationRole, member.role_id).title if member else None


def test_founding_needs_companions_and_a_name(client, db_session):
    campaign, character, transported = _started_world(client, db_session)

    alone = player_guilds.found_guild(db_session, campaign["id"], character, "Fundamos uma guilda")
    assert not alone.changed and "mais um transportado" in alone.summary

    _travel_with(db_session, campaign, character, transported[RiskTolerance.BOLD])
    nameless = player_guilds.found_guild(db_session, campaign["id"], character, "Fundamos uma guilda")
    assert not nameless.changed and "nome da guilda" in nameless.summary

    taken = player_guilds.found_guild(
        db_session, campaign["id"], character,
        f'Fundamos uma guilda chamada "{db_session.query(Organization).first().name}"',
    )
    assert not taken.changed and "Já existe" in taken.summary


def test_a_hunters_guild_is_born_informal_and_the_party_keeps_travelling(client, db_session):
    campaign, character, transported = _started_world(client, db_session)
    bram = transported[RiskTolerance.BOLD]
    _travel_with(db_session, campaign, character, bram)
    group_id = character_group(db_session, character).id

    change = player_guilds.found_guild(
        db_session, campaign["id"], character,
        'Fundamos uma guilda de caçadores chamada "Lobos Cinzentos"',
    )

    assert change.changed
    guild = _guild(db_session)
    assert (guild.name, guild.focus, guild.organization_type) == (
        "Lobos Cinzentos", GuildFocus.HUNTERS, OrganizationType.GUILD
    )
    assert guild.formality == OrganizationFormality.INFORMAL
    assert guild.visibility == OrganizationVisibility.PRIVATE
    assert _role_of(db_session, guild, character.id) == "Mestre da Guilda"
    assert _role_of(db_session, guild, bram.id) == "Membro Fundador"
    assert db_session.get(Group, group_id).status == GroupStatus.ACTIVE

    social = client.get(
        f"/api/campaigns/{campaign['id']}/social", params={"character_id": character.id}
    ).json()
    assert any(org["name"] == "Lobos Cinzentos" and org["role"] == "Mestre da Guilda"
               for org in social["organizations"])


def test_bandit_crews_are_secret_unregistrable_and_refused_by_the_cautious(client, db_session):
    campaign, character, transported = _started_world(client, db_session)
    _travel_with(
        db_session, campaign, character,
        transported[RiskTolerance.BOLD], transported[RiskTolerance.CAUTIOUS],
    )

    change = player_guilds.found_guild(
        db_session, campaign["id"], character, 'Fundamos um bando chamado "Mãos Sujas"'
    )

    guild = _guild(db_session)
    assert change.changed and "não quer se envolver" in change.summary
    assert guild.focus == GuildFocus.BANDITS and guild.organization_type == OrganizationType.CRIMINAL
    assert guild.visibility == OrganizationVisibility.SECRET
    assert _role_of(db_session, guild, character.id) == "Líder do Bando"
    assert _role_of(db_session, guild, transported[RiskTolerance.CAUTIOUS].id) is None
    refused = player_guilds.formalize(db_session, campaign["id"], character)
    assert not refused.changed and "bando" in refused.summary


def test_recruiting_respects_consent_and_the_informal_cap(client, db_session, monkeypatch):
    campaign, character, transported = _started_world(client, db_session)
    bram, dessa, corren = (
        transported[RiskTolerance.BOLD], transported[RiskTolerance.CAUTIOUS],
        transported[RiskTolerance.BALANCED],
    )
    _travel_with(db_session, campaign, character, bram)
    player_guilds.found_guild(db_session, campaign["id"], character, 'Fundamos a guilda "Forja"')
    monkeypatch.setattr(player_guilds, "INFORMAL_MEMBER_CAP", 3)

    stranger = player_guilds.recruit(db_session, campaign["id"], character, dessa)
    assert not stranger.changed and "não conhece" in stranger.summary

    players_service.meet_simulated_player(db_session, campaign["id"], character.id, dessa.id)
    assert player_guilds.recruit(db_session, campaign["id"], character, dessa).changed
    assert _role_of(db_session, _guild(db_session), dessa.id) == "Membro"

    players_service.meet_simulated_player(db_session, campaign["id"], character.id, corren.id)
    capped = player_guilds.recruit(db_session, campaign["id"], character, corren)
    assert not capped.changed and "informal" in capped.summary

    expelled = player_guilds.expel(db_session, character, dessa)
    assert expelled.changed and _role_of(db_session, _guild(db_session), dessa.id) is None


def test_registering_with_the_council_makes_the_guild_public(client, db_session, monkeypatch):
    campaign, character, transported = _started_world(client, db_session)
    bram, dessa, corren = (
        transported[RiskTolerance.BOLD], transported[RiskTolerance.CAUTIOUS],
        transported[RiskTolerance.BALANCED],
    )
    _travel_with(db_session, campaign, character, bram)
    player_guilds.found_guild(db_session, campaign["id"], character, 'Fundamos a guilda "Forja"')
    guild = _guild(db_session)

    too_small = player_guilds.formalize(db_session, campaign["id"], character)
    assert not too_small.changed and "ao menos 3 membros" in too_small.summary

    players_service.meet_simulated_player(db_session, campaign["id"], character.id, dessa.id)
    player_guilds.recruit(db_session, campaign["id"], character, dessa)
    unknown = player_guilds.formalize(db_session, campaign["id"], character)
    assert not unknown.changed and "reputação" in unknown.summary

    adventurers = db_session.query(Organization).filter(
        Organization.name.like("Guilda de Aventureiros%")
    ).one()
    award_organization_reputation(
        db_session, adventurers, CombatActorType.CHARACTER, character.id,
        delta=5, reason="Concluiu contratos.",
    )
    change = player_guilds.formalize(db_session, campaign["id"], character)

    assert change.changed
    assert guild.formality == OrganizationFormality.FORMALLY_RECOGNIZED
    assert guild.visibility == OrganizationVisibility.PUBLIC
    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").one()
    assert knows(db_session, KnowerType.NPC, elder.id, f"organization:{guild.id}:exists", campaign["id"])

    monkeypatch.setattr(player_guilds, "INFORMAL_MEMBER_CAP", 3)
    players_service.meet_simulated_player(db_session, campaign["id"], character.id, corren.id)
    assert player_guilds.recruit(db_session, campaign["id"], character, corren).changed


def test_a_departing_leader_hands_over_and_an_empty_guild_ends(client, db_session):
    campaign, character, transported = _started_world(client, db_session)
    bram = transported[RiskTolerance.BOLD]
    _travel_with(db_session, campaign, character, bram)
    player_guilds.found_guild(db_session, campaign["id"], character, 'Fundamos a guilda "Forja"')
    guild = _guild(db_session)

    left = leave_organization(db_session, campaign["id"], character, "Saio da minha guilda")

    assert left.changed and bram.name in left.summary
    assert _role_of(db_session, guild, bram.id) == "Mestre da Guilda"

    bram_member = db_session.query(OrganizationMember).filter(
        OrganizationMember.member_id == bram.id,
        OrganizationMember.organization_id == guild.id,
    ).one()
    from app.game.organizations.roles import set_membership_status

    set_membership_status(db_session, bram_member, OrganizationMembershipStatus.LEFT)
    player_guilds.handle_departure(db_session, guild, bram_member)
    assert guild.status == OrganizationStatus.DISBANDED


def test_founding_through_the_engine(client, db_session):
    campaign, character, transported = _started_world(client, db_session)
    _travel_with(db_session, campaign, character, transported[RiskTolerance.BOLD])
    db_session.commit()

    class Parser(LLMService):
        def generate(self, system, prompt):
            if "Ação do jogador" in prompt:
                return json.dumps({"intent": "TALK", "target": None})
            return "Os dois apertam as mãos."

    llm = Parser()
    result = engine.resolve_action(
        db_session, llm, campaign["id"], character.id,
        "Fundamos uma guilda de pesquisadores chamada Olhos do Vale.", intent_llm_service=llm,
    )

    assert result.intent_type == "FOUND_ORGANIZATION"
    guild = _guild(db_session)
    assert (guild.name, guild.focus) == ("Olhos do Vale", GuildFocus.RESEARCHERS)
    assert guild.organization_type == OrganizationType.ACADEMIC
